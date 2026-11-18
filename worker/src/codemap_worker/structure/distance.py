"""구조 거리: 호출·import 그래프를 무방향으로 본 최단 홉 수. (Phase 5 어긋남 탐지에서 쓴다)"""

from collections import defaultdict, deque
from collections.abc import Iterable

from codemap_worker.models import GraphEdge

STRUCTURE_KINDS = frozenset({"call", "import"})
MAX_HOPS = 4


class StructureGraph:
    """call·import 엣지만으로 인접 목록을 한 번 만들어 두고 여러 쌍의 거리를 묻는다."""

    def __init__(self, edges: Iterable[GraphEdge]) -> None:
        self._adj: dict[str, set[str]] = defaultdict(set)
        for e in edges:
            if e.kind in STRUCTURE_KINDS and e.source != e.target:
                self._adj[e.source].add(e.target)
                self._adj[e.target].add(e.source)

    def distance(self, a: str, b: str, max_hops: int = MAX_HOPS) -> int | None:
        """a에서 b까지 홉 수. 같은 노드면 0, max_hops 안에 닿지 않거나 없는 노드면 None(연결 없음 = ∞)."""
        if a == b:
            return 0 if a in self._adj else None
        if a not in self._adj or b not in self._adj:
            return None
        seen = {a}
        frontier = deque([(a, 0)])
        while frontier:
            node, hops = frontier.popleft()
            if hops == max_hops:
                continue
            for nxt in self._adj[node]:
                if nxt == b:
                    return hops + 1
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, hops + 1))
        return None


def structural_distance(edges: Iterable[GraphEdge], a: str, b: str, max_hops: int = MAX_HOPS) -> int | None:
    """한 쌍만 물을 때의 편의 함수. 여러 쌍이면 StructureGraph를 한 번 만들어 쓴다."""
    return StructureGraph(edges).distance(a, b, max_hops)
