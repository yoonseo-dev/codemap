"""로컬 폴더를 구조 분석한다 (DB·큐 없이). 해석 성공률을 올릴 때 쓰는 도구.

    python -m codemap_worker.structure <폴더> [--top 20]
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from codemap_worker.ingest.files import collect_files
from codemap_worker.structure.analyze import analyze
from codemap_worker.structure.parse import parse_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="폴더 하나를 구조 분석한다")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--top", type=int, default=20, help="해석 못 한 호출 이름을 몇 개까지 보여 줄까")
    ap.add_argument("--max-file-kb", type=int, default=1024)
    ap.add_argument("--exclude-tests", action="store_true", help="테스트 파일을 빼고 분석한다 (진단용)")
    args = ap.parse_args(argv)

    root: Path = args.folder
    if not root.is_dir():
        print(f"폴더가 아니에요: {root}", file=sys.stderr)
        return 2

    started = time.monotonic()
    collected = collect_files(root, args.max_file_kb)
    sources = [f for f in collected.files if not (args.exclude_tests and _is_test(f.path))]
    symbols = [parse_file(f.path, (root / f.path).read_bytes(), f.language) for f in sources]
    parsed = time.monotonic()
    result = analyze(symbols)
    done = time.monotonic()

    m = result.metrics
    print(f"파일 {len(collected.files)}개 (건너뜀: 큰 파일 {collected.skipped_large}, 링크 {collected.skipped_symlink})")
    print(result.detail())
    print(f"파싱 {parsed - started:.1f}초, 해석 {done - parsed:.1f}초")
    print("지표:", {k: m[k] for k in sorted(m)})

    print("해석 성공률(테스트 파일 제외):", _rate(result, lambda p: not _is_test(p)),
          "| 테스트 파일만:", _rate(result, _is_test))
    kinds = Counter(e.kind for e in result.edges)
    print("엣지:", dict(kinds))
    modules = Counter(n.module_id for n in result.nodes)
    print(f"모듈 {len(modules)}개:", ", ".join(f"{k}({v})" for k, v in modules.most_common(12)))
    print(f"\n해석 못 한 호출 상위 {args.top}개 (이름이 프로젝트 안에 있는데 못 찾은 것):")
    for name, count in result.unresolved_names.most_common(args.top):
        print(f"  {count:5d}  {name}")
    return 0


def _is_test(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (any(p in ("test", "tests", "testing") for p in parts[:-1])
            or name.startswith("test_") or name.endswith(("_test.py", "test.java", "tests.java")))


def _rate(result, include) -> str:
    c: Counter = Counter()
    for path, counts in result.by_file.items():
        if include(path):
            c.update(counts)
    attempted = c["resolved"] + c["unresolved"] + c["ambiguous"]
    return f"{c['resolved'] / attempted:.0%} ({c['resolved']:,}/{attempted:,})" if attempted else "해당 없음"


if __name__ == "__main__":
    raise SystemExit(main())
