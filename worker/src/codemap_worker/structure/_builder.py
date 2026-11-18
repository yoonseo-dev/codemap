"""두 언어 파서가 함께 쓰는 정의 수집·ID 부여."""

from dataclasses import dataclass, field

from codemap_worker.structure.model import CallSite, Definition

_SIMPLE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_."


_COMMENTS = frozenset({"comment", "line_comment", "block_comment"})


def arg_count(arguments) -> int | None:
    """argument_list 노드의 인자 수 (주석 제외). 노드가 없으면 None."""
    if arguments is None:
        return None
    return sum(1 for c in arguments.named_children if c.type not in _COMMENTS)


def simple_dotted(text: str) -> bool:
    """`self`, `obj`, `pkg.util`처럼 점으로 이어진 이름뿐인가 (호출·괄호·대괄호가 없는가)."""
    return bool(text) and text[0] not in "0123456789." and all(c in _SIMPLE for c in text)


@dataclass
class RawDef:
    name: str
    kind: str
    container: tuple[str, ...]
    start_line: int
    end_line: int
    params: int | None = None
    # (name, receiver, line, is_constructor, arity)
    calls: list[tuple[str, str | None, int, bool, int | None]] = field(default_factory=list)
    var_types: dict[str, str] = field(default_factory=dict)  # 변수 이름 → 선언 타입 (Java)


# 노드로 만들지 않는 영역(익명 클래스·enum 상수 본문 등)의 호출을 버리는 자리표시자
OPAQUE = RawDef("<opaque>", "function", (), 0, 0)


def assign_ids(
    path: str, raws: list[RawDef], language: str
) -> tuple[list[Definition], list[CallSite], list[tuple[str, str, str]]]:
    """소스 순서대로 ID를 정한다. 같은 입력이면 언제나 같은 ID가 나온다.

    `path::Class.method`. 같은 ID가 겹치면:
      - Java: 겹치는 정의 모두에 `(파라미터 수)`를 붙이고(오버로드), 그래도 겹치면 둘째부터 `#2`, `#3`
      - Python: 첫 번째는 그대로 두고 둘째부터 `#2`, `#3` (예: property getter·setter)
    """
    base = [f"{path}::{'.'.join((*r.container, r.name))}" for r in raws]
    count: dict[str, int] = {}
    for b in base:
        count[b] = count.get(b, 0) + 1

    ids: list[str] = []
    for r, b in zip(raws, base, strict=True):
        ids.append(f"{b}({r.params})" if count[b] > 1 and language == "java" and r.params is not None else b)

    seen: dict[str, int] = {}
    final: list[str] = []
    for i in ids:
        seen[i] = seen.get(i, 0) + 1
        final.append(i if seen[i] == 1 else f"{i}#{seen[i]}")

    definitions = [
        Definition(
            id=fid, name=r.name, qualified_name=".".join((*r.container, r.name)), kind=r.kind,
            start_line=r.start_line, end_line=r.end_line, container=r.container, params=r.params,
        )
        for r, fid in zip(raws, final, strict=True)
    ]
    calls = [
        CallSite(caller_id=fid, name=n, receiver=recv, line=line, is_constructor=ctor, arity=arity)
        for r, fid in zip(raws, final, strict=True)
        for (n, recv, line, ctor, arity) in r.calls
    ]
    var_types = [(fid, var, typ) for r, fid in zip(raws, final, strict=True) for var, typ in r.var_types.items()]
    return definitions, calls, var_types
