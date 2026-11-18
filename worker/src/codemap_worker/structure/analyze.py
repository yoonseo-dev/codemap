"""구조 분석 조립: 파싱된 파일들 → 노드·엣지·지표."""

from collections import Counter
from dataclasses import dataclass, field

from codemap_worker.models import GraphEdge, GraphNode
from codemap_worker.structure.model import FileSymbols
from codemap_worker.structure.modules import compute_modules
from codemap_worker.structure.resolve import resolve


@dataclass(frozen=True)
class StructureResult:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metrics: dict[str, float]
    unresolved_names: Counter = field(default_factory=Counter)
    by_file: dict = field(default_factory=dict)  # 파일 → {resolved, unresolved, ambiguous, external} 호출 수

    def detail(self) -> str:
        rate = self.metrics.get("resolvedRate")
        rate_text = f"{round(rate * 100)}%" if rate is not None else "해당 없음"
        return (f"함수 {self.metrics['functions']:,.0f}개, 호출 관계 {self.metrics['edges']:,.0f}개, "
                f"해석 성공률 {rate_text}")


def analyze(files: list[FileSymbols]) -> StructureResult:
    res = resolve(files)
    modules = compute_modules([f.path for f in files])

    edges = [GraphEdge(src, dst, "call", float(n)) for (src, dst), n in res.call_edges.items()]
    edges += [GraphEdge(src, dst, "import", 1.0) for (src, dst) in res.import_edges]
    edges.sort(key=lambda e: (e.kind, e.source, e.target))

    degree: Counter = Counter()
    for e in edges:
        degree[e.source] += 1
        degree[e.target] += 1

    nodes = [
        GraphNode(
            id=d.id, name=d.qualified_name, path=f.path, module_id=modules[f.path], kind=d.kind,
            start_line=d.start_line, end_line=d.end_line, degree=degree[d.id], sem=None,
        )
        for f in sorted(files, key=lambda f: f.path)
        for d in f.definitions
    ]

    c = res.counts
    attempted = c["callResolved"] + c["callUnresolved"] + c["callAmbiguous"]
    metrics: dict[str, float] = {
        "functions": len(nodes),
        "edges": len(edges),
        "callResolved": c["callResolved"],
        "callUnresolved": c["callUnresolved"],
        "callAmbiguous": c["callAmbiguous"],
        "callExternal": c["callExternal"],
        "callOverloadGuess": c["callOverloadGuess"],  # 같은 클래스의 오버로드 중 첫 번째로 연결한 호출 수
        "importResolved": c["importResolved"],
        "importUnresolved": c["importUnresolved"],
        "importExternal": c["importExternal"],
        "importWildcard": c["importWildcard"],
        "parseErrors": sum(f.parse_errors for f in files),
        "modules": len(set(modules.values())),
    }
    if attempted:  # 분모가 0이면 성공률을 만들지 않는다 (1.0이라고 거짓말하지 않기)
        metrics["resolvedRate"] = round(c["callResolved"] / attempted, 2)
    return StructureResult(nodes, edges, metrics, res.unresolved_names, dict(res.by_file))
