"""가짜 의미·역사 생성기: 실제 노드 위에 만들고, 결정적이고, 엣지 수가 노드 수에 비례해야 한다."""

from collections import Counter

import pytest

from codemap_worker.fake_graph import fake_history, fake_semantic
from codemap_worker.models import GraphEdge, GraphNode
from codemap_worker.structure.distance import StructureGraph


def make_nodes(n: int, modules: int = 6) -> list[GraphNode]:
    return [
        GraphNode(id=f"m{i % modules}/f.py::fn{i}", name=f"fn{i}", path=f"m{i % modules}/f.py",
                  module_id=f"m{i % modules}/", kind="function", start_line=1, end_line=3, degree=i % 7)
        for i in range(n)
    ]


def make_calls(nodes: list[GraphNode]) -> list[GraphEdge]:
    return [GraphEdge(nodes[i].id, nodes[(i * 7 + 3) % len(nodes)].id, "call", 1.0)
            for i in range(len(nodes)) if nodes[i].id != nodes[(i * 7 + 3) % len(nodes)].id]


def test_same_input_gives_same_output():
    nodes = make_nodes(120)
    calls = make_calls(nodes)
    assert fake_semantic(nodes, "abc") == fake_semantic(nodes, "abc")
    assert fake_history(nodes, calls, "abc") == fake_history(nodes, calls, "abc")
    assert fake_semantic(nodes, "abc") != fake_semantic(nodes, "other-commit")


def test_a_nodes_position_does_not_change_when_other_nodes_are_added():
    nodes = make_nodes(60)
    more = nodes + make_nodes(80)[60:]
    pos_a, _ = fake_semantic(nodes, "s")
    pos_b, _ = fake_semantic(more, "s")
    # 모듈 수가 같으면 중심이 같아, 기존 노드의 좌표는 새 노드와 무관하다(재분석해도 화면이 덜 흔들린다)
    assert all(pos_a[n.id] == pos_b[n.id] for n in nodes)


def test_every_node_gets_a_position_and_every_edge_connects_real_distinct_nodes():
    nodes = make_nodes(150)
    ids = {n.id for n in nodes}
    positions, similar = fake_semantic(nodes, "s")
    cochange = fake_history(nodes, make_calls(nodes), "s")

    assert set(positions) == ids and all(len(p) == 3 for p in positions.values())
    for e in (*similar, *cochange):
        assert e.source in ids and e.target in ids and e.source != e.target
    assert len({(e.source, e.target) for e in similar}) == len(similar)  # 중복 없음
    assert len({(e.source, e.target) for e in cochange}) == len(cochange)


def test_edge_fields_follow_the_contract():
    nodes = make_nodes(150)
    _, similar = fake_semantic(nodes, "s")
    cochange = fake_history(nodes, make_calls(nodes), "s")
    assert similar and cochange
    assert all(e.kind == "similar" and 0 <= e.weight <= 1 and e.since is None for e in similar)
    assert all(e.kind == "cochange" and 0 <= e.weight <= 1 for e in cochange)
    assert all(e.since is not None and e.since.tzinfo is not None for e in cochange)


def test_cochange_includes_pairs_with_no_structural_connection():
    nodes = make_nodes(200)
    calls = make_calls(nodes)
    g = StructureGraph(calls)
    cochange = fake_history(nodes, calls, "s")
    hidden = [e for e in cochange if g.distance(e.source, e.target, max_hops=1) is None]
    assert hidden, "숨은 결합처럼 보이는 쌍이 하나도 없다"
    # 숨은 결합은 서로 다른 모듈의 함수끼리다
    module = {n.id: n.module_id for n in nodes}
    assert all(module[e.source] != module[e.target] for e in hidden)


@pytest.mark.parametrize("n", [3, 200, 3000])
def test_edge_counts_scale_with_node_count_instead_of_exploding(n):
    nodes = make_nodes(n)
    _, similar = fake_semantic(nodes, "s")
    cochange = fake_history(nodes, make_calls(nodes), "s")
    assert len(similar) <= n  # 노드 수보다 많지 않다
    assert len(cochange) <= n


def test_tiny_graphs_do_not_crash():
    assert fake_semantic([], "s") == ({}, [])
    assert fake_history([], [], "s") == []
    one = make_nodes(1, modules=1)
    positions, similar = fake_semantic(one, "s")
    assert len(positions) == 1 and similar == []
    assert fake_history(one, [], "s") == []


def test_similar_edges_are_mostly_inside_modules_with_some_across():
    nodes = make_nodes(300)
    module = {n.id: n.module_id for n in nodes}
    _, similar = fake_semantic(nodes, "s")
    kinds = Counter("same" if module[e.source] == module[e.target] else "cross" for e in similar)
    assert kinds["same"] > kinds["cross"] > 0
