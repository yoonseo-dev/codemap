"""분석할 소스 파일(.java, .py) 목록. 제외 폴더·심볼릭 링크·큰 파일은 뺀다."""

import os
from dataclasses import dataclass
from pathlib import Path

from codemap_worker.models import StageError

LANGUAGES = {".java": "java", ".py": "python"}

EXCLUDED_DIRS = frozenset({
    ".git", "node_modules", "venv", ".venv", "build", "target", "dist", "__pycache__",
    ".tox", ".gradle", ".idea",
})


@dataclass(frozen=True)
class SourceFile:
    path: str  # 저장소 루트 기준, `/` 구분
    language: str  # java | python
    size: int


@dataclass(frozen=True)
class CollectedFiles:
    files: list[SourceFile]
    skipped_large: int
    skipped_symlink: int


def collect_files(root: Path, max_file_kb: int) -> CollectedFiles:
    files: list[SourceFile] = []
    skipped_large = skipped_symlink = 0
    stack = [(str(root), "")]
    while stack:
        current, rel = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                skipped_symlink += 1  # 저장소 밖을 가리킬 수 있어 따라가지 않는다
                continue
            child_rel = f"{rel}{entry.name}"
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in EXCLUDED_DIRS:
                    stack.append((entry.path, child_rel + "/"))
                continue
            language = LANGUAGES.get(os.path.splitext(entry.name)[1])
            if language is None:
                continue
            size = entry.stat(follow_symlinks=False).st_size
            if size > max_file_kb * 1024:
                skipped_large += 1
                continue
            files.append(SourceFile(child_rel, language, size))
    files.sort(key=lambda f: f.path)
    return CollectedFiles(files, skipped_large, skipped_symlink)


def require_sources(collected: CollectedFiles) -> None:
    if not collected.files:
        raise StageError("UNSUPPORTED_LANGUAGE", "Java·Python 파일을 찾지 못했어요", resumable=False)
