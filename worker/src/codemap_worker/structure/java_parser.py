"""Java 소스 → 정의·호출·import (tree-sitter)."""

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from codemap_worker.structure._builder import OPAQUE, RawDef, arg_count, assign_ids, simple_dotted
from codemap_worker.structure.model import FileSymbols, ImportRef

_PARSER = Parser(Language(tree_sitter_java.language()))

_TYPE_DECLS = frozenset({
    "class_declaration", "interface_declaration", "enum_declaration", "record_declaration",
    "annotation_type_declaration",
})
_METHODS = frozenset({"method_declaration", "constructor_declaration"})


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


def parse_java(path: str, source: bytes) -> FileSymbols:
    tree = _PARSER.parse(source)
    raws: list[RawDef] = []
    imports: list[ImportRef] = []
    package: str | None = None
    fields: dict[tuple[str, ...], dict[str, str]] = {}  # 클래스 → {필드 이름: 선언 타입}

    stack: list[tuple[Node, tuple[str, ...], RawDef | None]] = [(tree.root_node, (), None)]
    while stack:
        node, classes, current = stack.pop()
        t = node.type
        child_classes, child_current = classes, current

        if t == "package_declaration":
            package = next((_text(c) for c in node.named_children if c.type != "annotation"), None)
            continue
        if t == "import_declaration":
            imports.append(_import(node))
            continue

        if t in _TYPE_DECLS:
            if current is None:  # 메서드 안의 지역 클래스는 노드를 만들지 않는다
                child_classes = (*classes, _text(node.child_by_field_name("name")))
        elif t in _METHODS:
            if current is None:  # 익명 클래스·지역 클래스 안의 메서드는 바깥 메서드의 일부
                raw = RawDef(
                    name=_text(node.child_by_field_name("name")),
                    kind="method",
                    container=classes,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    params=_param_count(node),
                )
                raws.append(raw)
                child_current = raw
        elif t == "field_declaration" and current is None and classes:
            _bind_declaration(node, fields.setdefault(classes, {}))
        elif t in ("local_variable_declaration", "enhanced_for_statement", "resource") and current is not None:
            _bind_declaration(node, current.var_types)
        elif t in ("formal_parameter", "spread_parameter") and current is not None:
            _bind_parameter(node, current.var_types)
        elif t == "class_body" and current is None and node.parent is not None \
                and node.parent.type in ("object_creation_expression", "enum_constant"):
            child_current = OPAQUE  # 익명 클래스·enum 상수 본문: 노드를 만들지 않는다
        elif t == "method_invocation":
            if current is not None:
                _record_invocation(node, current)
        elif t == "object_creation_expression":
            if current is not None:
                _record_creation(node, current)
        elif (
            t == "explicit_constructor_invocation"
            and current is not None
            and classes
            and node.children
            and node.children[0].type == "this"
        ):
            # this(...)는 같은 클래스의 다른 생성자 호출. super(...)는 부모 클래스를 모르므로 세지 않는다.
            args = next((c for c in node.children if c.type == "argument_list"), None)
            current.calls.append((classes[-1], None, node.start_point[0] + 1, True, arg_count(args)))

        for child in reversed(node.children):
            stack.append((child, child_classes, child_current))

    definitions, calls, var_types = assign_ids(path, raws, "java")
    var_types += [(f"class:{'.'.join(cls)}", var, typ) for cls, vs in fields.items() for var, typ in vs.items()]
    return FileSymbols(
        path=path, language="java", definitions=tuple(definitions), calls=tuple(calls),
        var_types=tuple(var_types),
        imports=tuple(sorted(imports, key=lambda i: i.line)), package=package,
        parse_errors=1 if tree.root_node.has_error else 0,
    )


def _param_count(node: Node) -> int:
    params = node.child_by_field_name("parameters")
    if params is None:
        return 0
    return sum(1 for c in params.named_children if c.type in ("formal_parameter", "spread_parameter"))


def _record_invocation(node: Node, current: RawDef) -> None:
    name = _text(node.child_by_field_name("name"))
    obj = node.child_by_field_name("object")
    receiver: str | None
    if obj is None:
        receiver = None
    else:
        text = _text(obj)
        receiver = text if simple_dotted(text) else ""
    current.calls.append((name, receiver, node.start_point[0] + 1, False,
                          arg_count(node.child_by_field_name("arguments"))))


def _record_creation(node: Node, current: RawDef) -> None:
    type_node = node.child_by_field_name("type")
    name = _simple_type_name(type_node)
    if name:
        current.calls.append((name, None, node.start_point[0] + 1, True,
                              arg_count(node.child_by_field_name("arguments"))))


def _declared_type(node: Node | None) -> str:
    """선언된 타입 이름. `List<String>` → List, `a.b.C` → a.b.C, 배열·기본형은 빈 문자열."""
    if node is None:
        return ""
    if node.type == "type_identifier":
        return _text(node)
    if node.type == "scoped_type_identifier":
        return _text(node)
    if node.type == "generic_type":
        return _declared_type(next((c for c in node.named_children if c.type != "type_arguments"), None))
    return ""


def _bind_parameter(node: Node, into: dict[str, str]) -> None:
    typ = _declared_type(node.child_by_field_name("type"))
    if node.type == "spread_parameter":  # String... rest → 배열이라 메서드 호출 대상이 아니다
        return
    name = _text(node.child_by_field_name("name"))
    if typ and name:
        into[name] = typ


def _bind_declaration(node: Node, into: dict[str, str]) -> None:
    """`Foo a = ..., b;`, `for (Foo x : xs)`, `try (Foo r = ...)`의 변수 이름 → 타입."""
    typ = _declared_type(node.child_by_field_name("type"))
    declarators = node.children_by_field_name("declarator")
    if node.type in ("enhanced_for_statement", "resource"):
        names = [(_text(node.child_by_field_name("name")), node.child_by_field_name("value"))]
    else:
        names = [(_text(d.child_by_field_name("name")), d.child_by_field_name("value")) for d in declarators]
    for name, value in names:
        t = typ
        if t == "var" and value is not None and value.type == "object_creation_expression":
            t = _simple_type_name(value.child_by_field_name("type"))  # `var x = new Foo()`의 Foo
        if t and t != "var" and name:
            into[name] = t


def _simple_type_name(node: Node | None) -> str:
    """`Inner<String>` → Inner, `a.b.Outer.Inner` → Inner"""
    if node is None:
        return ""
    if node.type == "type_identifier":
        return _text(node)
    if node.type == "generic_type":
        return _simple_type_name(next((c for c in node.named_children if c.type != "type_arguments"), None))
    if node.type == "scoped_type_identifier":
        last = node.named_children[-1] if node.named_children else None
        return _text(last) if last is not None and last.type == "type_identifier" else ""
    return ""


def _import(node: Node) -> ImportRef:
    line = node.start_point[0] + 1
    raw = _text(node).strip().removesuffix(";").strip()
    body = raw.removeprefix("import").strip()
    is_static = body.startswith("static ")
    body = body.removeprefix("static").strip()
    if body.endswith(".*"):
        return ImportRef(module=body[:-2].strip(), is_wildcard=True, is_static=is_static, line=line)
    if is_static:
        module, _, member = body.rpartition(".")
        return ImportRef(module=module, names=((member, None),), is_static=True, line=line)
    return ImportRef(module=body, line=line)
