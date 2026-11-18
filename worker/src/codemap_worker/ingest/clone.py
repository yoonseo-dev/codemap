"""저장소를 내려받아 작업 폴더에 분석할 커밋을 체크아웃한다."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from codemap_worker.ingest.git import (
    GitError,
    GitTimeout,
    GitTooLarge,
    dir_size_bytes,
    remove_tree,
    run_git,
)
from codemap_worker.models import StageError

_GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_DONE = ".codemap-complete"

# 분석에 필요한 소스만 받는다 (blobless clone + sparse checkout)
_SPARSE_PATTERNS = ["*.java", "*.py"]


@dataclass(frozen=True)
class IngestConfig:
    workdir: Path
    clone_timeout_seconds: float = 300
    max_repo_mb: int = 500
    max_file_kb: int = 1024
    max_commits: int = 2000
    bulk_threshold: int = 50
    allow_local_repos: bool = False

    @classmethod
    def from_settings(cls, s) -> "IngestConfig":
        return cls(
            workdir=Path(s.workdir),
            clone_timeout_seconds=s.clone_timeout_seconds,
            max_repo_mb=s.max_repo_mb,
            max_file_kb=s.max_file_kb,
            max_commits=s.max_commits,
            bulk_threshold=s.bulk_commit_file_threshold,
            allow_local_repos=s.allow_local_repos,
        )

    @property
    def max_bytes(self) -> int:
        return self.max_repo_mb * 1024 * 1024


def validate_repo_url(url: str, cfg: IngestConfig) -> str:
    """분석할 주소가 맞는지 확인하고, 작업 폴더 이름에 쓸 접두사를 돌려준다."""
    m = _GITHUB.match(url)
    if m:
        return f"{m.group(1)}__{m.group(2)}"
    if cfg.allow_local_repos and Path(url).exists():
        return "local__" + hashlib.sha1(url.encode()).hexdigest()[:8]
    raise StageError("CLONE_FAILED", "분석할 수 없는 저장소 주소예요", resumable=False)


def checkout_dir(url: str, sha: str, cfg: IngestConfig) -> Path:
    if not _SHA.match(sha):
        raise StageError("CLONE_FAILED", "커밋 주소가 올바르지 않아요", resumable=False)
    return cfg.workdir / f"{validate_repo_url(url, cfg)}@{sha[:12]}"


def ensure_checkout(url: str, sha: str, cfg: IngestConfig, on_progress=None) -> Path:
    """작업 폴더를 돌려준다. 이미 받아 둔 폴더(완료 표시가 있음)는 다시 받지 않는다."""
    dest = checkout_dir(url, sha, cfg)
    if (dest / _DONE).exists():
        return dest

    cfg.workdir.mkdir(parents=True, exist_ok=True)
    remove_tree(dest)  # 중간에 끊긴 폴더가 남아 있을 수 있다
    timeout = cfg.clone_timeout_seconds
    local = cfg.allow_local_repos
    try:
        run_git(
            ["clone", "--quiet", "--filter=blob:none", "--single-branch", "--no-tags",
             "--no-checkout", "--", url, str(dest)],
            timeout=timeout, allow_local=local, watch_dir=dest, max_bytes=cfg.max_bytes,
        )
        if on_progress:
            on_progress(0.6)
        run_git(["sparse-checkout", "init", "--no-cone"], cwd=dest, timeout=timeout, allow_local=local)
        run_git(["sparse-checkout", "set", "--no-cone", *_SPARSE_PATTERNS],
                cwd=dest, timeout=timeout, allow_local=local)
        run_git(["checkout", "--quiet", "--detach", sha],
                cwd=dest, timeout=timeout, allow_local=local, watch_dir=dest, max_bytes=cfg.max_bytes)
        if dir_size_bytes(dest) > cfg.max_bytes:
            raise GitTooLarge("작업 폴더가 한도를 넘었어요")
    except GitTooLarge:
        remove_tree(dest)
        raise StageError("REPO_TOO_LARGE", f"저장소가 너무 커요 ({cfg.max_repo_mb}MB 초과)",
                         resumable=False) from None
    except GitTimeout:
        remove_tree(dest)
        raise StageError("CLONE_TIMEOUT", "저장소를 받는 데 너무 오래 걸려요", resumable=True) from None
    except GitError as e:
        remove_tree(dest)
        raise StageError("CLONE_FAILED", "저장소를 내려받지 못했어요", resumable=True) from e

    (dest / _DONE).write_text(sha, encoding="utf-8")
    return dest
