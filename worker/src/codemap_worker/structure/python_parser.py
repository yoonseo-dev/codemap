"""Python 소스 → 정의·호출·import (tree-sitter)."""

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from codemap_worker.structure._builder import RawDef, arg_count, assign_ids, simple_dotted
from codemap_worker.structure.model import FileSymbols, ImportRef

_PARSER = Parser(Language(tree_sitter_python.language()))


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


def parse_python(path: str, source: bytes) -> FileSymbols:
    tree = _PARSER.parse(source)
    raws: list[RawDef] = []
    imports: list[ImportRef] = []

    # (노드, 감싸는 클래스들, 지금 속한 정의). 반복문으로 돌려 깊은 식에서도 재귀 한도에 걸리지 않는다.
    stack: list[tuple[Node, tuple[str, ...], RawDef | None]] = [(tree.root_node, (), None)]
    while stack:
        node, classes, current = stack.pop()
        t = node.type
        child_classes, child_current = classes, current

        if t == "class_definition":
            if current is None:  # 함수 안의 클래스는 노드를 만들지 않는다
                child_classes = (*classes, _text(node.child_by_field_name("name")))
        elif t == "function_definition":
            if current is None:  # 중첩 함수는 노드가 아니라 바깥 정의의 일부
                raw = RawDef(
                    name=_text(node.child_by_field_name("name")),
                    kind="method" if classes else "function",
                    container=classes,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
                raws.append(raw)
                child_current = raw
        elif t == "call":
            if current is not None:
                _record_call(node, current)
        elif t in ("import_statement", "import_from_statement"):
            imports.extend(_imports(node))
            continue

        for child in reversed(node.children):
            stack.append((child, child_classes, child_current))

    definitions, calls, _ = assign_ids(path, raws, "python")
    return FileSymbols(
        path=path, language="python", definitions=tuple(definitions), calls=tuple(calls),
        imports=tuple(sorted(imports, key=lambda i: i.line)),
        parse_errors=1 if tree.root_node.has_error else 0,
    )


def _record_call(node: Node, current: RawDef) -> None:
    fn = node.child_by_field_name("function")
    if fn is None:
        return
    line = node.start_point[0] + 1
    arity = arg_count(node.child_by_field_name("arguments"))
    if fn.type == "identifier":
        current.calls.append((_text(fn), None, line, False, arity))
    elif fn.type == "attribute":
        obj = _text(fn.child_by_field_name("object"))
        current.calls.append((_text(fn.child_by_field_name("attribute")),
                              obj if simple_dotted(obj) else "", line, False, arity))
    # `f()()`처럼 호출 결과를 또 부르는 식은 안쪽 호출만 센다


def _imports(node: Node) -> list[ImportRef]:
    line = node.start_point[0] + 1
    if node.type == "import_statement":
        out = []
        for child in node.children_by_field_name("name"):
            if child.type == "aliased_import":
                out.append(ImportRef(module=_text(child.child_by_field_name("name")),
                                     alias=_text(child.child_by_field_name("alias")), line=line))
            else:
                out.append(ImportRef(module=_text(child), line=line))
        return out

    # from X import a, b as c / from . import x / from m import *
    module_node = node.child_by_field_name("module_name")
    level, module = 0, ""
    if module_node is not None:
        if module_node.type == "relative_import":
            for child in module_node.children:
                if child.type == "import_prefix":
                    level = len(_text(child))
                elif child.type == "dotted_name":
                    module = _text(child)
        else:
            module = _text(module_node)
    names: list[tuple[str, str | None]] = []
    wildcard = False
    for child in node.children:
        if child.type == "wildcard_import":
            wildcard = True
    for child in node.children_by_field_name("name"):
        if child.type == "aliased_import":
            names.append((_text(child.child_by_field_name("name")), _text(child.child_by_field_name("alias"))))
        else:
            names.append((_text(child), None))
    return [ImportRef(module=module, names=tuple(names), is_wildcard=wildcard, level=level, line=line)]
