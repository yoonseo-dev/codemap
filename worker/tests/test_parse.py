"""파서 단위 테스트: 픽스처 저장소(py_shop, java_shop)와 경계 사례."""

from pathlib import Path

import pytest

from codemap_worker.structure.model import ImportRef
from codemap_worker.structure.parse import parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def load(repo: str, rel: str):
    root = FIXTURES / repo
    language = "java" if rel.endswith(".java") else "python"
    return parse_file(rel.replace("\\", "/"), (root / rel).read_bytes(), language)


def summary(f):
    """(정의 ID 접미사, 시작·끝 줄)과 (호출한 정의, 수신자, 이름, 줄) 목록."""
    defs = [(d.id.split("::")[1], d.kind, d.start_line, d.end_line) for d in f.definitions]
    calls = [(c.caller_id.split("::")[1], c.receiver, c.name, c.line, c.is_constructor) for c in f.calls]
    return defs, calls


def py(source: str):
    return parse_file("m.py", source.encode(), "python")


def java(source: str):
    return parse_file("M.java", source.encode(), "java")


# ---------- 픽스처: Python ----------

def test_python_fixture_definitions_calls_and_imports():
    f = load("py_shop", "billing/invoice.py")

    defs, calls = summary(f)
    assert defs == [
        ("InvoiceService.create", "method", 9, 12),
        ("InvoiceService.calc_total", "method", 14, 15),
        ("helper", "function", 18, 20),
    ]
    assert calls == [
        ("InvoiceService.create", "self", "calc_total", 10, False),
        ("InvoiceService.create", "mailer", "send", 11, False),
        ("InvoiceService.calc_total", None, "sum_items", 15, False),
        ("InvoiceService.calc_total", None, "rate_for", 15, False),
        ("helper", None, "print", 19, False),
        ("helper", "tax", "rate_for", 20, False),
    ]
    assert f.imports == (
        ImportRef(module="notify.mailer", alias="mailer", line=1),
        ImportRef(module="billing", names=(("tax", None),), line=2),
        ImportRef(module="orders.cart", names=(("sum_items", None),), line=3),
        ImportRef(module="tax", names=(("rate_for", None),), level=1, line=5),
    )
    assert f.parse_errors == 0 and f.package is None
    assert f.definitions[0].id == "billing/invoice.py::InvoiceService.create"


def test_python_fixture_module_functions():
    defs, calls = summary(load("py_shop", "billing/tax.py"))
    assert defs == [("rate_for", "function", 1, 2), ("lookup", "function", 5, 6)]
    assert calls == [("rate_for", None, "lookup", 2, False), ("lookup", None, "len", 6, False)]


def test_empty_init_file_has_nothing():
    f = load("py_shop", "billing/__init__.py")
    assert (f.definitions, f.calls, f.imports) == ((), (), ())


# ---------- 픽스처: Java ----------

def test_java_fixture_overloads_constructors_and_nested_class():
    f = load("java_shop", "src/main/java/com/shop/billing/Invoice.java")

    defs, calls = summary(f)
    assert defs == [
        ("Invoice.Invoice(0)", "method", 11, 13),
        ("Invoice.Invoice(1)", "method", 15, 17),
        ("Invoice.total(0)", "method", 19, 22),
        ("Invoice.total(1)", "method", 24, 26),
        ("Invoice.init", "method", 28, 30),
        ("Invoice.Line.amount", "method", 33, 35),
    ]
    assert calls == [
        ("Invoice.Invoice(0)", None, "Invoice", 12, True),  # this(1)
        ("Invoice.Invoice(1)", None, "init", 16, False),
        ("Invoice.total(0)", "cart", "sumItems", 20, False),
        ("Invoice.total(0)", None, "rateFor", 21, False),
        ("Invoice.total(1)", None, "total", 25, False),
        ("Invoice.init", "Mailer", "send", 29, False),
        ("Invoice.Line.amount", "Tax", "rateFor", 34, False),
    ]
    assert f.package == "com.shop.billing"
    assert f.imports == (
        ImportRef(module="com.shop.billing.Tax", names=(("rateFor", None),), is_static=True, line=3),
        ImportRef(module="com.shop.orders.Cart", line=5),
        ImportRef(module="com.shop.notify", is_wildcard=True, line=6),
    )
    # 필드 초기화(`new Cart()`)는 어느 메서드에도 속하지 않아 호출로 세지 않는다
    assert not any(c.name == "Cart" for c in f.calls)
    assert f.definitions[0].id == "src/main/java/com/shop/billing/Invoice.java::Invoice.Invoice(0)"


def test_java_fixture_interface_with_static_and_abstract_methods():
    defs, calls = summary(load("java_shop", "src/main/java/com/shop/notify/Mailer.java"))
    assert [d[0] for d in defs] == ["Mailer.send", "Mailer.format", "Mailer.deliver"]
    assert ("Mailer.send", None, "format", 5, False) in calls
    assert ("Mailer.send", "System.out", "println", 5, False) in calls


# ---------- 경계 사례: Python ----------

def test_python_nested_function_is_part_of_the_outer_definition():
    f = py("def outer():\n    def inner():\n        deep()\n    inner()\n")
    defs, calls = summary(f)
    assert [d[0] for d in defs] == ["outer"]
    assert [(c[2]) for c in calls] == ["deep", "inner"]


def test_python_lambda_calls_belong_to_the_enclosing_function():
    f = py("def f(xs):\n    return sorted(xs, key=lambda x: score(x))\n")
    assert [c.name for c in f.calls] == ["sorted", "score"]


def test_python_property_setter_gets_a_numbered_id():
    f = py("class A:\n    @property\n    def x(self): return 1\n    @x.setter\n    def x(self, v): pass\n")
    assert [d.id for d in f.definitions] == ["m.py::A.x", "m.py::A.x#2"]
    assert [d.start_line for d in f.definitions] == [3, 5]  # 데코레이터가 아니라 def 줄


def test_python_decorated_and_async_definitions_start_at_the_def_line():
    f = py("@deco\n@other(1)\nasync def run():\n    await go()\n")
    assert [(d.name, d.start_line, d.end_line) for d in f.definitions] == [("run", 3, 4)]
    assert [c.name for c in f.calls] == ["go"]


def test_python_module_and_class_level_calls_are_ignored():
    f = py("setup()\nclass A:\n    x = make()\n    def m(self):\n        real()\nif True:\n    boot()\n")
    assert [c.name for c in f.calls] == ["real"]


def test_python_class_inside_a_function_is_not_a_node():
    f = py("def factory():\n    class Local:\n        def m(self):\n            go()\n    return Local\n")
    assert [d.id for d in f.definitions] == ["m.py::factory"]
    assert [c.name for c in f.calls] == ["go"]


def test_python_nested_classes_use_dotted_ids():
    f = py("class Outer:\n    class Inner:\n        def m(self): pass\n")
    assert [d.id for d in f.definitions] == ["m.py::Outer.Inner.m"]
    assert f.definitions[0].container == ("Outer", "Inner")


def test_python_complex_receivers_and_call_results():
    f = py("def f(a):\n    a.b().c()\n    x[0].d()\n    g()()\n    pkg.sub.run()\n")
    got = [(c.receiver, c.name) for c in f.calls]
    assert ("pkg.sub", "run") in got
    assert ("", "c") in got and ("", "d") in got  # 복잡한 식은 수신자를 ""로 표시
    assert [n for r, n in got if r is None] == ["g"]  # g()()의 바깥 호출은 세지 않는다


@pytest.mark.parametrize(("source", "expected"), [
    ("import a.b.c", [ImportRef(module="a.b.c", line=1)]),
    ("import os, sys as s", [ImportRef(module="os", line=1), ImportRef(module="sys", alias="s", line=1)]),
    ("from . import x", [ImportRef(module="", names=(("x", None),), level=1, line=1)]),
    ("from .. import y", [ImportRef(module="", names=(("y", None),), level=2, line=1)]),
    ("from ..pkg.mod import y as z", [ImportRef(module="pkg.mod", names=(("y", "z"),), level=2, line=1)]),
    ("from m import (a, b as c)", [ImportRef(module="m", names=(("a", None), ("b", "c")), line=1)]),
    ("from m import *", [ImportRef(module="m", is_wildcard=True, line=1)]),
])
def test_python_import_forms(source, expected):
    assert list(py(source).imports) == expected


def test_python_imports_inside_functions_are_found():
    f = py("def f():\n    import json\n    from os import path\n")
    assert [i.module for i in f.imports] == ["json", "os"]


# ---------- 경계 사례: Java ----------

def test_java_overloads_with_same_parameter_count_get_numbered_ids():
    f = java("class A { void a(int x) {} void a(String s) {} void b() {} }")
    assert [d.id for d in f.definitions] == ["M.java::A.a(1)", "M.java::A.a(1)#2", "M.java::A.b"]


def test_java_varargs_count_as_one_parameter():
    f = java("class A { void a(int x, String... rest) {} void a(int x) {} }")
    assert [d.params for d in f.definitions] == [2, 1]


def test_java_anonymous_and_local_classes_belong_to_the_enclosing_method():
    f = java(
        "class A {\n"
        "  Object field = new Object() { void fa() { never(); } };\n"
        "  void m() {\n"
        "    new Thread() { void inAnon() { hidden(); } };\n"
        "    class Local { void lm() { local(); } }\n"
        "  }\n"
        "}\n"
    )
    assert [d.id for d in f.definitions] == ["M.java::A.m"]
    assert sorted(c.name for c in f.calls) == ["Thread", "hidden", "local"]


def test_java_enum_interface_and_record_members():
    f = java(
        "enum E { A { void x() { ignored(); } }, B; void ev() { go(); } }\n"
        "interface I { void im(); default void dm() { zed(); } }\n"
        "record R(int a) { void rm() { r(); } }\n"
    )
    assert [d.id for d in f.definitions] == [
        "M.java::E.ev", "M.java::I.im", "M.java::I.dm", "M.java::R.rm",
    ]
    assert sorted(c.name for c in f.calls) == ["go", "r", "zed"]  # enum 상수 본문(ignored)은 버린다


def test_java_constructor_calls_use_the_simple_class_name():
    f = java("class A { void m() { new Foo<String>(); new a.b.Outer.Inner(); new int[3]; } }")
    assert [(c.name, c.is_constructor) for c in f.calls] == [("Foo", True), ("Inner", True)]


def test_java_package_is_none_when_absent_and_imports_are_parsed():
    f = java("import a.b.C;\nimport static a.b.D.*;\nclass A {}\n")
    assert f.package is None
    assert f.imports == (
        ImportRef(module="a.b.C", line=1),
        ImportRef(module="a.b.D", is_wildcard=True, is_static=True, line=2),
    )


def test_java_receivers():
    f = java("class A { void m() { foo(); this.bar(); super.baz(); X.y(); a.b.c.z(); list.stream().map(f); } }")
    assert [(c.receiver, c.name) for c in f.calls] == [
        (None, "foo"), ("this", "bar"), ("super", "baz"), ("X", "y"), ("a.b.c", "z"), ("", "map"), ("list", "stream"),
    ]


# ---------- 견고함과 결정성 ----------

def test_syntax_errors_do_not_stop_parsing_and_are_counted():
    f = py("def f(:\n    pass\n\ndef g():\n    h()\n")
    assert f.parse_errors == 1
    f2 = java("class A { void ok() { fine(); } void broken( { } }")
    assert f2.parse_errors == 1
    assert any(d.name == "ok" for d in f2.definitions)


def test_invalid_utf8_bytes_do_not_crash():
    f = parse_file("m.py", b"def f():\n    x = '\xff\xfe'\n    g()\n", "python")
    assert [d.name for d in f.definitions] == ["f"]
    assert [c.name for c in f.calls] == ["g"]


def test_empty_and_whitespace_files():
    for src in (b"", b"\n\n", b"# only a comment\n"):
        f = parse_file("m.py", src, "python")
        assert (f.definitions, f.calls, f.parse_errors) == ((), (), 0)


def test_very_deep_expression_does_not_hit_the_recursion_limit():
    f = py("def f():\n    return " + "+".join(["a"] * 5000) + "\n")
    assert [d.name for d in f.definitions] == ["f"]


def test_same_input_gives_same_ids_and_results():
    src = "class A:\n    def x(self): pass\n    def x(self): pass\n    def y(self): z()\n"
    assert py(src) == py(src)
    j = "class A { void a(int x) {} void a(int y) {} }"
    assert java(j) == java(j)


def test_unsupported_language_is_an_error():
    with pytest.raises(ValueError):
        parse_file("a.go", b"package main", "go")
