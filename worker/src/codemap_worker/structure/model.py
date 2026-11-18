"""파일 하나를 파싱한 결과. 다른 파일이나 디스크를 모른다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Definition:
    """함수 또는 메서드 하나. 클래스는 정의가 아니라 container(소속)로만 나타난다."""

    id: str  # 파일경로::Class.method (중복이면 `(n)`·`#k` 접미사)
    name: str
    qualified_name: str  # Class.method 또는 function
    kind: str  # function | method
    start_line: int  # 1부터
    end_line: int  # 끝 줄 포함
    container: tuple[str, ...] = ()  # 소속 클래스 이름들 (바깥 → 안쪽)
    params: int | None = None  # Java 오버로드 구분용 파라미터 수


@dataclass(frozen=True)
class CallSite:
    """정의 안에서 일어난 호출 하나."""

    caller_id: str
    name: str  # 부르는 이름 (함수명, 메서드명, 생성자면 클래스명)
    # None: 수신자 없음(`f()`), "": 복잡한 식(`a().b()`), 그 외: 점으로 이어진 이름(`self`, `obj`, `pkg.util`)
    receiver: str | None
    line: int
    is_constructor: bool = False


@dataclass(frozen=True)
class ImportRef:
    """import 한 줄. 어느 파일로 이어지는지는 해석 단계에서 정한다."""

    module: str  # Python: `a.b` (상대 import면 점 뒤의 부분, 없으면 ""), Java: `a.b.C` 또는 패키지 `a.b`
    names: tuple[tuple[str, str | None], ...] = ()  # (가져온 이름, 별칭). `from m import x as y`
    alias: str | None = None  # `import a.b as ab`의 ab
    is_wildcard: bool = False
    level: int = 0  # Python 상대 import의 점 개수 (절대 import는 0)
    is_static: bool = False  # Java `import static`
    line: int = 0


@dataclass(frozen=True)
class FileSymbols:
    path: str
    language: str  # java | python
    definitions: tuple[Definition, ...] = ()
    calls: tuple[CallSite, ...] = ()
    imports: tuple[ImportRef, ...] = ()
    package: str | None = None  # Java package
    parse_errors: int = 0  # 문법 오류가 있어 일부만 읽은 파일이면 1
