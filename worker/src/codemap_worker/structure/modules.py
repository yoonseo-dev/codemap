"""파일 경로 → 모듈(폴더 묶음) ID. 지도에서 같은 색으로 묶이는 단위다.

실제 저장소는 `src/main/java/com/google/gson/...`처럼 경로가 깊어서 맨 앞 폴더로 묶으면 전부 한 덩어리다.
1. 소스 루트(`src/main/java/`, `src/test/java/`, `src/`)까지 떼고,
2. 모든 파일이 공통으로 가진 앞 폴더(`com/google/gson/`)도 떼고,
3. 남은 경로의 앞 2단계를 모듈 ID로 한다. 폴더가 없으면 `(root)/`.
4. 모듈이 너무 적으면(MIN_MODULES 미만) 충분해질 때까지 깊이를 하나씩 늘린다.
"""

_SOURCE_ROOTS = (("src", "main", "java"), ("src", "test", "java"), ("src", "main", "python"), ("src",))
ROOT_MODULE = "(root)/"
DEPTH = 2
MAX_DEPTH = 5
MIN_MODULES = 5


def _strip_source_root(parts: list[str]) -> list[str]:
    for root in _SOURCE_ROOTS:
        n = len(root)
        for i in range(len(parts) - n):  # 마지막 원소는 파일 이름이라 제외
            if tuple(parts[i : i + n]) == root:
                return parts[i + n :]
    return parts


def compute_modules(paths: list[str], depth: int | None = None) -> dict[str, str]:
    """depth를 주면 그 깊이로 고정한다. 없으면 모듈이 MIN_MODULES개 이상이 되는 가장 얕은 깊이(2~MAX_DEPTH)를 쓴다.
    끝까지 못 닿으면 모듈이 가장 많은 깊이 중 가장 얕은 것."""
    rests = _rest_dirs(paths)
    if depth is not None:
        return _by_depth(rests, depth)
    best: dict[str, str] = {}
    for d in range(DEPTH, MAX_DEPTH + 1):
        current = _by_depth(rests, d)
        if len(set(current.values())) >= MIN_MODULES:
            return current
        if len(set(current.values())) > len(set(best.values())):
            best = current
    return best


def _rest_dirs(paths: list[str]) -> dict[str, list[str]]:
    dirs = {p: _strip_source_root(p.split("/"))[:-1] for p in paths}
    non_empty = [d for d in dirs.values() if d]
    common: list[str] = []
    for level in zip(*non_empty, strict=False):
        if len(set(level)) != 1:
            break
        common.append(level[0])
    # 모든 파일이 정확히 같은 폴더 하나에 있을 때만 그 폴더를 남긴다(아니면 모듈이 하나뿐이라 의미가 없다).
    if non_empty and len({tuple(d) for d in non_empty}) == 1:
        common = common[:-1]
    return {p: (d[len(common):] if d[: len(common)] == common else d) for p, d in dirs.items()}


def _by_depth(rests: dict[str, list[str]], depth: int) -> dict[str, str]:
    return {p: ("/".join(rest[:depth]) + "/" if rest else ROOT_MODULE) for p, rest in rests.items()}
