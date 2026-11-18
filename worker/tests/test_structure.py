"""해석(import·호출 엣지, 지표), 모듈 분류, 구조 거리 테스트."""

from pathlib import Path

import pytest

from codemap_worker.ingest.files import collect_files
from codemap_worker.models import GraphEdge
from codemap_worker.structure.analyze import analyze
from codemap_worker.structure.distance import StructureGraph, structural_distance
from codemap_worker.structure.modules import compute_modules
from codemap_worker.structure.parse import parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    root = FIXTURES / name
    files = collect_files(root, 1024).files
    return analyze([parse_file(f.path, (root / f.path).read_bytes(), f.language) for f in files])


def project(sources: dict[str, str]):
    return analyze([
        parse_file(path, text.encode(), "java" if path.endswith(".java") else "python")
        for path, text in sources.items()
    ])


def calls(result) -> set[tuple[str, str]]:
    """(호출한 정의, 호출된 정의) — 파일 경로 접두사를 뗀 짧은 이름."""
    return {(_short(e.source), _short(e.target)) for e in result.edges if e.kind == "call"}


def imports(result) -> set[tuple[str, str]]:
    return {(_short(e.source), _short(e.target)) for e in result.edges if e.kind == "import"}


def _short(node_id: str) -> str:
    path, name = node_id.split("::")
    return f"{path.rsplit('/', 1)[-1].split('.')[0]}.{name}"


# ---------- 픽스처: Python ----------

def test_python_fixture_graph():
    r = fixture("py_shop")

    assert {n.id for n in r.nodes} == {
        "billing/invoice.py::InvoiceService.create", "billing/invoice.py::InvoiceService.calc_total",
        "billing/invoice.py::helper", "billing/tax.py::rate_for", "billing/tax.py::lookup",
        "orders/cart.py::sum_items", "orders/cart.py::price", "notify/mailer.py::send",
        "notify/mailer.py::format_message",
    }
    assert calls(r) == {
        ("invoice.InvoiceService.create", "invoice.InvoiceService.calc_total"),  # self.calc_total
        ("invoice.InvoiceService.create", "mailer.send"),  # import notify.mailer as mailer
        ("invoice.InvoiceService.calc_total", "cart.sum_items"),  # from orders.cart import sum_items
        ("invoice.InvoiceService.calc_total", "tax.rate_for"),  # from .tax import rate_for (상대 import)
        ("invoice.helper", "tax.rate_for"),  # from billing import tax → tax.rate_for (하위 모듈)
        ("tax.rate_for", "tax.lookup"),
        ("cart.sum_items", "cart.price"),
        ("mailer.send", "mailer.format_message"),
    }
    # import 엣지: 출발은 import한 파일의 대표 노드(가장 먼저 정의된 것), 도착은 가져온 심볼 또는 그 파일의 대표 노드
    assert imports(r) == {
        ("invoice.InvoiceService.create", "mailer.send"),
        ("invoice.InvoiceService.create", "tax.rate_for"),
        ("invoice.InvoiceService.create", "cart.sum_items"),
    }
    m = r.metrics
    assert (m["callResolved"], m["callUnresolved"], m["callAmbiguous"], m["callExternal"]) == (8, 0, 0, 3)
    assert m["resolvedRate"] == 1.0  # print, len, str는 외부 호출이라 분모에서 빠진다
    assert (m["importResolved"], m["importExternal"], m["importUnresolved"]) == (4, 0, 0)
    assert {n.module_id for n in r.nodes} == {"billing/", "orders/", "notify/"}
    assert r.detail() == "함수 9개, 호출 관계 11개, 해석 성공률 100%"


def test_degree_counts_call_and_import_edges_at_both_ends():
    r = fixture("py_shop")
    by_id = {n.id: n for n in r.nodes}
    # create: 호출 2개(출발) + import 3개(출발)
    assert by_id["billing/invoice.py::InvoiceService.create"].degree == 5
    assert all(n.degree == sum(1 for e in r.edges if n.id in (e.source, e.target)) for n in r.nodes)
    assert all(n.sem is None for n in r.nodes)  # 의미 좌표는 아직 없다


# ---------- 픽스처: Java ----------

def test_java_fixture_graph():
    r = fixture("java_shop")

    base = "src/main/java/com/shop/"
    assert len(r.nodes) == 14
    assert calls(r) == {
        ("Invoice.Invoice.Invoice(0)", "Invoice.Invoice.Invoice(1)"),  # this(1) → 인자 1개인 생성자
        ("Invoice.Invoice.Invoice(1)", "Invoice.Invoice.init"),
        ("Invoice.Invoice.total(0)", "Cart.Cart.sumItems"),  # 필드 `Cart cart`의 선언 타입 + 단일 import
        ("Invoice.Invoice.total(0)", "Tax.Tax.rateFor"),  # import static
        ("Invoice.Invoice.total(1)", "Invoice.Invoice.total(0)"),  # 인자 수로 오버로드 선택
        ("Invoice.Invoice.init", "Mailer.Mailer.send"),  # 와일드카드 import + 클래스 이름으로 부른 정적 메서드
        ("Invoice.Invoice.Line.amount", "Tax.Tax.rateFor"),  # 같은 패키지
        ("Tax.Tax.rateFor", "Tax.Tax.lookup"),
        ("Cart.Cart.sumItems", "Cart.Cart.price"),
        ("Mailer.Mailer.send", "Mailer.Mailer.format"),
    }
    assert imports(r) == {
        ("Invoice.Invoice.Invoice(0)", "Tax.Tax.rateFor"),  # import static: 메서드가 하나라 그 메서드로
        ("Invoice.Invoice.Invoice(0)", "Cart.Cart.sumItems"),  # import com.shop.orders.Cart: 파일의 대표 노드
    }
    m = r.metrics
    assert (m["callResolved"], m["callUnresolved"], m["callAmbiguous"], m["callExternal"]) == (10, 0, 0, 2)
    assert m["importWildcard"] == 1 and m["resolvedRate"] == 1.0
    assert {n.module_id for n in r.nodes} == {"billing/", "orders/", "notify/"}
    assert all(n.path.startswith(base) for n in r.nodes)


# ---------- 해석 규칙 ----------

def test_repeated_calls_add_up_to_the_edge_weight_and_recursion_makes_no_edge():
    r = project({"a.py": "def f():\n    g()\n    g()\n    f()\n\ndef g():\n    pass\n"})
    [edge] = [e for e in r.edges if e.kind == "call"]
    assert (edge.source, edge.target, edge.weight) == ("a.py::f", "a.py::g", 2.0)
    assert r.metrics["callResolved"] == 3  # 재귀 호출도 해석은 성공으로 센다


def test_unknown_names_are_external_and_leave_the_rate_alone():
    r = project({"a.py": "def f():\n    print(1)\n    len([])\n    helper()\n\ndef helper():\n    pass\n"})
    m = r.metrics
    assert (m["callResolved"], m["callExternal"], m["callUnresolved"]) == (1, 2, 0)
    assert m["resolvedRate"] == 1.0


def test_known_name_on_an_unknown_receiver_counts_as_unresolved():
    r = project({"a.py": "def f(obj):\n    obj.run()\n\nclass K:\n    def run(self):\n        pass\n"})
    assert (r.metrics["callUnresolved"], r.metrics["callResolved"]) == (1, 0)
    assert r.metrics["resolvedRate"] == 0.0
    assert r.unresolved_names["obj.run"] == 1


def test_no_attempted_calls_means_no_rate_instead_of_a_fake_100_percent():
    r = project({"a.py": "def f():\n    print(1)\n"})
    assert "resolvedRate" not in r.metrics
    assert r.detail().endswith("해석 성공률 해당 없음")


def test_candidates_in_different_files_are_ambiguous_and_make_no_edge():
    r = project({
        "a.py": "from x import *\nfrom y import *\ndef f():\n    dup()\n",
        "x.py": "def dup():\n    pass\n",
        "y.py": "def dup():\n    pass\n",
    })
    assert r.metrics["callAmbiguous"] == 1
    assert not [e for e in r.edges if e.kind == "call"]


def test_python_name_resolution_prefers_the_same_file_over_imports():
    r = project({
        "a.py": "from b import go\ndef go():\n    pass\ndef f():\n    go()\n",
        "b.py": "def go():\n    pass\n",
    })
    assert calls(r) == {("a.f", "a.go")}


def test_python_class_constructor_goes_to_init_and_methods_to_self():
    r = project({
        "a.py": ("class A:\n    def __init__(self):\n        self.setup()\n    def setup(self):\n        pass\n"
                 "def make():\n    A()\n"),
    })
    assert calls(r) == {("a.A.__init__", "a.A.setup"), ("a.make", "a.A.__init__")}


def test_python_class_without_init_has_no_node_to_link_and_is_not_counted_as_failure():
    r = project({"a.py": "class Plain:\n    def m(self):\n        pass\ndef f():\n    Plain()\n"})
    assert r.metrics["callExternal"] == 1 and r.metrics["callUnresolved"] == 0


def test_python_reexported_symbol_is_followed_through_the_package_init():
    r = project({
        "pkg/__init__.py": "from .core import run\n",
        "pkg/core.py": "def run():\n    pass\n",
        "app.py": "import pkg\nfrom pkg import run\ndef a():\n    pkg.run()\ndef b():\n    run()\n",
    })
    assert calls(r) == {("app.a", "core.run"), ("app.b", "core.run")}


def test_python_module_name_prefers_the_source_root_over_a_nearby_namesake():
    # 실제 프로젝트(flask)에서 겪은 문제: tests 아래 flask.py가 진짜 패키지 src/flask를 가렸다
    r = project({
        "src/flask/__init__.py": "from .app import Flask\n",
        "src/flask/app.py": "class Flask:\n    def __init__(self):\n        pass\n",
        "tests/test_a.py": "import flask\ndef t():\n    flask.Flask()\n",
        "tests/apps/inner/flask.py": "def other():\n    pass\n",
    })
    assert ("test_a.t", "app.Flask.__init__") in calls(r)


def test_python_external_imports_are_external_not_unresolved():
    r = project({
        "a.py": ("import os\nimport numpy as np\nfrom os import path\n"
                 "def f():\n    os.getcwd()\n    np.array([])\n    path.join('a')\n"
                 "def array():\n    pass\ndef join():\n    pass\ndef getcwd():\n    pass\n"),
    })
    m = r.metrics
    assert (m["callExternal"], m["callUnresolved"]) == (3, 0)
    assert m["importExternal"] == 3


def test_relative_imports_that_go_nowhere_are_unresolved_not_external():
    r = project({"pkg/a.py": "from .missing import thing\nfrom ... import far\n"})
    assert r.metrics["importUnresolved"] == 2 and r.metrics["importExternal"] == 0


def test_python_import_of_a_module_adds_an_edge_to_that_files_first_node():
    r = project({"a.py": "import b\ndef f():\n    pass\n", "b.py": "def first():\n    pass\ndef second():\n    pass\n"})
    assert imports(r) == {("a.f", "b.first")}


def test_java_overloads_choose_by_argument_count():
    r = project({"A.java": "class A { void f(int a) {} void f(int a, int b) {} void g() { f(1); f(1, 2); } }"})
    assert calls(r) == {("A.A.g", "A.A.f(1)"), ("A.A.g", "A.A.f(2)")}
    assert r.metrics["callOverloadGuess"] == 0


def test_java_same_arity_overloads_in_one_class_link_to_the_first_and_are_counted():
    r = project({"A.java": "class A { void f(int a) {} void f(String s) {} void g() { f(1); } }"})
    assert calls(r) == {("A.A.g", "A.A.f(1)")}
    assert r.metrics["callOverloadGuess"] == 1 and r.metrics["callAmbiguous"] == 0


def test_java_same_name_in_two_wildcard_packages_is_ambiguous():
    r = project({
        "p/A.java": "package p;\nimport x.*;\nimport y.*;\nclass A { void m() { new Dup(); } }",
        "x/Dup.java": "package x;\npublic class Dup { public Dup() {} }",
        "y/Dup.java": "package y;\npublic class Dup { public Dup() {} }",
    })
    assert r.metrics["callAmbiguous"] == 1


def test_java_variable_types_come_from_declarations_params_and_this_fields():
    r = project({
        "A.java": ("class A {\n  private B b;\n  void m(C c) { B local = new B(); local.one(); c.two(); this.b.three(); b.three(); }\n}"),
        "B.java": "class B { void one() {} void three() {} }",
        "C.java": "class C { void two() {} }",
    })
    assert {("A.A.m", "B.B.one"), ("A.A.m", "C.C.two")} <= calls(r)
    # this.b.three() 는 점이 둘이라 해석하지 않고, b.three() 만 필드 타입으로 푼다
    assert ("A.A.m", "B.B.three") in calls(r)


def test_java_receiver_of_a_known_external_type_is_external():
    r = project({"A.java": "class A { void m(String s, StringBuilder sb) { s.length(); sb.append(1); Math.max(1, 2); } void length() {} void append(int x) {} void max(int a, int b) {} }"})
    assert (r.metrics["callExternal"], r.metrics["callUnresolved"]) == (3, 0)


def test_java_unqualified_call_searches_the_enclosing_classes_outward():
    r = project({"A.java": "class A { void outer() {} class In { void m() { outer(); } } }"})
    assert calls(r) == {("A.A.In.m", "A.A.outer")}


def test_results_are_deterministic_and_sorted():
    sources = {"b.py": "def g():\n    pass\n", "a.py": "from b import g\ndef f():\n    g()\n"}
    r1, r2 = project(sources), project(dict(reversed(list(sources.items()))))
    assert [n.id for n in r1.nodes] == [n.id for n in r2.nodes]
    assert r1.edges == r2.edges
    assert r1.edges == sorted(r1.edges, key=lambda e: (e.kind, e.source, e.target))


def test_nodes_use_qualified_names_and_edges_connect_existing_nodes():
    r = fixture("py_shop")
    ids = {n.id for n in r.nodes}
    assert all(e.source in ids and e.target in ids and e.source != e.target for e in r.edges)
    assert {n.name for n in r.nodes} >= {"InvoiceService.create", "helper"}


# ---------- 모듈 분류 ----------

def test_modules_strip_source_roots_and_the_common_package_prefix():
    paths = [
        "gson/src/main/java/com/google/gson/Gson.java",
        "gson/src/main/java/com/google/gson/internal/Streams.java",
        "gson/src/main/java/com/google/gson/internal/bind/ArrayTypeAdapter.java",
        "gson/src/main/java/com/google/gson/reflect/TypeToken.java",
        "gson/src/test/java/com/google/gson/GsonTest.java",
    ]
    m = compute_modules(paths)
    assert m[paths[0]] == "(root)/"
    assert m[paths[1]] == "internal/"
    assert m[paths[2]] == "internal/bind/"
    assert m[paths[3]] == "reflect/"
    assert m[paths[4]] == "(root)/"  # 테스트도 같은 패키지이면 같은 모듈


def test_modules_go_deeper_when_a_multi_module_repo_would_collapse_into_one_blob():
    # 실제 gson: 예제·템플릿 폴더 때문에 공통 접두사가 없고, 2단계(com/google/)만으로는 전부 한 덩어리가 된다
    paths = [
        "gson/src/main/java/com/google/gson/Gson.java",
        "gson/src/main/java/com/google/gson/internal/Streams.java",
        "gson/src/main/java/com/google/gson/reflect/TypeToken.java",
        "gson/src/main/java/com/google/gson/stream/JsonReader.java",
        "gson/src/test/java/com/google/gson/functional/MapTest.java",
        "examples/android/src/main/java/com/example/Demo.java",
        "gson/src/main/java-templates/com/google/gson/Version.java",
    ]
    modules = set(compute_modules(paths).values())
    assert len(modules) >= 5
    assert {"com/google/gson/internal/", "com/google/gson/reflect/"} <= modules


def test_modules_for_a_python_src_layout():
    paths = ["src/flask/app.py", "src/flask/json/tag.py", "tests/test_basic.py", "examples/tutorial/db.py"]
    m = compute_modules(paths)
    assert m["src/flask/app.py"] == "flask/"
    assert m["src/flask/json/tag.py"] == "flask/json/"
    assert m["tests/test_basic.py"] == "tests/"
    assert m["examples/tutorial/db.py"] == "examples/tutorial/"


def test_modules_when_everything_lives_in_one_folder_keep_one_level():
    m = compute_modules(["pkg/a.py", "pkg/b.py"])
    assert set(m.values()) == {"pkg/"}


def test_root_level_files_go_to_the_root_module():
    assert compute_modules(["setup.py", "pkg/a.py"])["setup.py"] == "(root)/"


# ---------- 구조 거리 ----------

def _edges(*pairs, kind="call"):
    return [GraphEdge(a, b, kind, 1.0) for a, b in pairs]


def test_structural_distance_counts_hops_ignoring_direction():
    edges = _edges(("a", "b"), ("b", "c"), ("d", "c"), ("d", "e"), ("e", "f"))
    g = StructureGraph(edges)
    assert g.distance("a", "b") == 1
    assert g.distance("b", "a") == 1  # 방향 무시
    assert g.distance("a", "c") == 2
    assert g.distance("a", "d") == 3
    assert g.distance("a", "e") == 4
    assert g.distance("a", "f") is None  # 5홉은 연결 없음(∞)
    assert g.distance("a", "f", max_hops=5) == 5


def test_structural_distance_edge_cases():
    g = StructureGraph(_edges(("a", "b")) + _edges(("x", "y"), kind="similar"))
    assert g.distance("a", "a") == 0
    assert g.distance("a", "zzz") is None  # 없는 노드
    assert g.distance("zzz", "zzz") is None
    assert g.distance("x", "y") is None  # similar·cochange는 구조 거리에 쓰지 않는다
    assert structural_distance(_edges(("a", "b"), ("b", "c")), "a", "c") == 2


def test_structural_distance_handles_cycles():
    g = StructureGraph(_edges(("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")))
    assert g.distance("a", "d") == 2


@pytest.mark.parametrize("name", ["py_shop", "java_shop"])
def test_fixture_distance_is_usable_on_real_results(name):
    r = fixture(name)
    g = StructureGraph(r.edges)
    first = r.nodes[0].id
    assert g.distance(first, first) in (0, None)
