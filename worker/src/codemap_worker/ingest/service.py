"""INGEST 단계 본체: clone → 커밋 정보 → 소스 파일 수집."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codemap_worker.ingest.clone import IngestConfig, ensure_checkout
from codemap_worker.ingest.files import CollectedFiles, collect_files, require_sources
from codemap_worker.ingest.info import CommitInfo, read_commit_info

Report = Callable[[int, str | None, dict[str, float]], None]


@dataclass(frozen=True)
class IngestResult:
    root: Path  # 체크아웃된 작업 폴더
    commit: CommitInfo
    collected: CollectedFiles

    def metrics(self) -> dict[str, float]:
        return {
            "commits": self.commit.commits,
            "bulkExcluded": self.commit.bulk_excluded,
            "sourceFiles": len(self.collected.files),
        }

    def detail(self) -> str:
        return f"커밋 {self.commit.commits:,}개를 받고 대량 커밋 {self.commit.bulk_excluded:,}개는 뺐어요"


def ingest(repo_url: str, sha: str, cfg: IngestConfig, report: Report) -> IngestResult:
    """실패하면 StageError(REPO_TOO_LARGE·UNSUPPORTED_LANGUAGE·CLONE_FAILED·CLONE_TIMEOUT)."""
    report(5, "저장소를 내려받는 중이에요", {})
    root = ensure_checkout(repo_url, sha, cfg)
    report(70, "커밋 이력을 읽는 중이에요", {})
    commit = read_commit_info(root, sha, cfg)
    report(90, "분석할 파일을 찾는 중이에요", {"commits": commit.commits})
    collected = collect_files(root, cfg.max_file_kb)
    require_sources(collected)
    result = IngestResult(root, commit, collected)
    report(100, result.detail(), result.metrics())
    return result
