"""파일 하나를 언어에 맞는 파서로 읽는다."""

from codemap_worker.structure.java_parser import parse_java
from codemap_worker.structure.model import FileSymbols
from codemap_worker.structure.python_parser import parse_python


def parse_file(path: str, source: bytes, language: str) -> FileSymbols:
    """문법 오류가 있어도 읽을 수 있는 만큼만 돌려준다 (parse_errors=1). 지원하지 않는 언어는 오류."""
    if language == "python":
        return parse_python(path, source)
    if language == "java":
        return parse_java(path, source)
    raise ValueError(f"지원하지 않는 언어: {language}")
