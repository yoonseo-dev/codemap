"""가짜 의미·역사 결과. 실제 노드 위에 만들고, 같은 입력이면 언제나 같은 결과가 나온다.

Phase 4(의미 지도), Phase 3(역사 지도)에서 진짜 분석으로 바뀌기 전까지 지도 화면이 동작하게 하는 자리 채움이다.
- 의미 좌표: 모듈마다 구(球) 위에 중심을 하나씩 두고, 그 주변에 노드를 흩뿌린다.
- similar 엣지: 같은 모듈 안 위주 + 모듈을 가로지르는 몇 쌍(중복 구현처럼 보이는 것).
- cochange 엣지: 호출 관계가 있는 쌍의 일부 + 호출 관계가 전혀 없는 쌍 몇 개(숨은 결합처럼 보이는 것).
엣지 수는 노드 수에 비례한다(노드가 수천 개여도 폭발하지 않는다).
"""

import math
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from codemap_worker.models import GraphEdge, GraphNode

_SPHERE_RADIUS = 3.0
_BASE_DATE = datetime(2025, 11, 1, tzinfo=UTC)
_STRUCTURE = ("call", "import")

Vec3 = tuple[float, float, float]


def fake_semantic(nodes: list[GraphNode], seed: str) -> tuple[dict[str, Vec3], list[GraphEdge]]:
    """(노드 ID → 가짜 의미 좌표, 가짜 similar 엣지)."""
    by_module: dict[str, list[GraphNode]] = defaultdict(list)
    for n in sorted(nodes, key=lambda n: n.id):
        by_module[n.module_id].append(n)
    modules = sorted(by_module)

    # 구 위에 모듈 중심을 골고루 놓는다 (황금각)
    centers: dict[str, Vec3] = {}
    for i, m in enumerate(modules):
        y = 1 - 2 * (i + 0.5) / len(modules)
        r = math.sqrt(max(0.0, 1 - y * y))
        theta = i * 2.399963229728653
        centers[m] = (_SPHERE_RADIUS * r * math.cos(theta), _SPHERE_RADIUS * y, _SPHERE_RADIUS * r * math.sin(theta))

    positions: dict[str, Vec3] = {}
    for m, members in by_module.items():
        cx, cy, cz = centers[m]
        for n in members:
            rnd = random.Random(f"{seed}|pos|{n.id}")  # 노드마다 따로 시드해, 다른 노드가 바뀌어도 이 노드는 그대로다
            spread = max(0.15, 0.8 / (1 + n.degree / 4))  # 연결이 많은 함수일수록 모듈 중심에 가깝다
            positions[n.id] = (
                round(cx + rnd.gauss(0, spread), 3),
                round(cy + rnd.gauss(0, spread), 3),
                round(cz + rnd.gauss(0, spread), 3),
            )

    seen: set[tuple[str, str]] = set()
    edges: list[GraphEdge] = []

    def add(a: str, b: str, weight: float) -> None:
        key = (a, b) if a < b else (b, a)
        if a != b and key not in seen:
            seen.add(key)
            edges.append(GraphEdge(key[0], key[1], "similar", round(weight, 2)))

    for m in modules:
        members = by_module[m]
        if len(members) < 2:
            continue
        rnd = random.Random(f"{seed}|sim|{m}")
        for _ in range(max(1, round(0.12 * len(members)))):
            a, b = rnd.sample(members, 2)
            add(a.id, b.id, rnd.uniform(0.70, 0.88))

    if len(modules) >= 2:
        rnd = random.Random(f"{seed}|dup")
        for _ in range(max(3, round(0.01 * len(nodes)))):
            m1, m2 = rnd.sample(modules, 2)
            add(rnd.choice(by_module[m1]).id, rnd.choice(by_module[m2]).id, rnd.uniform(0.88, 0.97))

    edges.sort(key=lambda e: (e.source, e.target))
    return positions, edges


def fake_history(nodes: list[GraphNode], edges: list[GraphEdge], seed: str) -> list[GraphEdge]:
    """가짜 cochange 엣지. `edges`는 실제 구조 엣지(call·import)다."""
    structure = sorted((e for e in edges if e.kind in _STRUCTURE), key=lambda e: (e.source, e.target, e.kind))
    connected = {(e.source, e.target) for e in structure} | {(e.target, e.source) for e in structure}
    out: dict[tuple[str, str], GraphEdge] = {}

    def since(rnd: random.Random) -> datetime:
        return _BASE_DATE + timedelta(days=rnd.randint(0, 330))

    rnd = random.Random(f"{seed}|co-struct")
    for e in structure:
        if e.kind == "call" and rnd.random() < 0.15:  # 같이 부르는 함수는 같이 수정되기 쉽다
            key = (e.source, e.target) if e.source < e.target else (e.target, e.source)
            out.setdefault(key, GraphEdge(key[0], key[1], "cochange", round(rnd.uniform(0.5, 0.9), 2), since(rnd)))

    ordered = sorted(nodes, key=lambda n: n.id)
    if len(ordered) >= 2:
        rnd = random.Random(f"{seed}|co-hidden")
        for _ in range(max(3, round(0.01 * len(ordered)))):
            for _attempt in range(20):  # 호출·import 관계가 없는 다른 모듈의 두 함수
                a, b = rnd.sample(ordered, 2)
                key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                if a.module_id != b.module_id and (a.id, b.id) not in connected and key not in out:
                    out[key] = GraphEdge(key[0], key[1], "cochange", round(rnd.uniform(0.6, 0.9), 2), since(rnd))
                    break

    return sorted(out.values(), key=lambda e: (e.source, e.target))
