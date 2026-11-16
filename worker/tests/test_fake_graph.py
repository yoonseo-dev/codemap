from collections import Counter

from codemap_worker.fake_graph import make_fake_graph


def test_is_deterministic():
    assert make_fake_graph() == make_fake_graph()


def test_node_ids_are_unique_and_edges_connect_real_nodes():
    nodes, edges = make_fake_graph()
    ids = [n.id for n in nodes]
    assert len(ids) == len(set(ids))
    known = set(ids)
    assert all(e.source in known and e.target in known and e.source != e.target for e in edges)
    keys = [(e.source, e.target, e.kind) for e in edges]
    assert len(keys) == len(set(keys))


def test_has_about_200_functions_in_6_modules_and_all_edge_kinds():
    nodes, edges = make_fake_graph()
    assert 150 <= len(nodes) <= 260
    assert len({n.module_id for n in nodes}) == 6
    assert set(Counter(e.kind for e in edges)) == {"call", "import", "similar", "cochange"}


def test_edge_fields_follow_the_contract():
    _nodes, edges = make_fake_graph()
    for e in edges:
        if e.kind in ("similar", "cochange"):
            assert 0 <= e.weight <= 1
        if e.kind == "cochange":
            assert e.since is not None and e.since.tzinfo is not None
        else:
            assert e.since is None


def test_degree_counts_structure_edges_only():
    nodes, edges = make_fake_graph()
    expected = Counter()
    for e in edges:
        if e.kind in ("call", "import"):
            expected[e.source] += 1
            expected[e.target] += 1
    assert all(n.degree == expected[n.id] for n in nodes)


def test_node_id_format_and_lines():
    nodes, _ = make_fake_graph()
    for n in nodes:
        path, _, name = n.id.partition("::")
        assert path == n.path and name == n.name and path.startswith(n.module_id)
        assert n.kind == ("method" if "." in name else "function")
        assert 1 <= n.start_line < n.end_line
