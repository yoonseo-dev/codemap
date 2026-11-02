import tree_sitter_java
import tree_sitter_python
from tree_sitter import Language, Parser


def test_tree_sitter_parses_java_and_python():
    java = Parser(Language(tree_sitter_java.language()))
    tree = java.parse(b"class A { void f() { g(); } }")
    assert tree.root_node.type == "program"

    python = Parser(Language(tree_sitter_python.language()))
    tree = python.parse(b"def f():\n    return g()\n")
    assert tree.root_node.type == "module"
