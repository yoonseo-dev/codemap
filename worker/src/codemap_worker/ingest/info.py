"""분석 커밋의 브랜치·시각, 최근 커밋 수와 대량 커밋 수."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from codemap_worker.ingest.clone import IngestConfig
from codemap_worker.ingest.git import GitError, run_git
from codemap_worker.models import StageError


@dataclass(frozen=True)
class CommitInfo:
    branch: str | None
    commit_date: datetime
    commits: int  # 최근 max_commits개 범위의 커밋 수 (머지 커밋 제외)
    bulk_excluded: int  # 그중 바꾼 파일이 bulk_threshold개 이상인 대량 커밋 수


def read_commit_info(repo: Path, sha: str, cfg: IngestConfig) -> CommitInfo:
    local = cfg.allow_local_repos
    t = cfg.clone_timeout_seconds
    try:
        date_text = run_git(["show", "-s", "--format=%cI", sha], cwd=repo, timeout=t, allow_local=local)
        commit_date = datetime.fromisoformat(date_text.strip())
        branch = _branch(repo, cfg)
        # 트리만 비교하는 이름 목록이라 blobless clone에서도 blob을 받지 않는다 (--no-renames 필수).
        log = run_git(
            ["log", sha, f"-n{cfg.max_commits}", "--no-merges", "--no-renames", "--name-only",
             "--format=@@%H"],
            cwd=repo, timeout=t, allow_local=local,
        )
    except (GitError, ValueError) as e:
        raise StageError("CLONE_FAILED", "커밋 정보를 읽지 못했어요", resumable=True) from e
    commits, bulk = count_commits(log, cfg.bulk_threshold)
    return CommitInfo(branch, commit_date, commits, bulk)


def count_commits(log: str, bulk_threshold: int) -> tuple[int, int]:
    """`--format=@@%H --name-only` 출력에서 (커밋 수, 대량 커밋 수)를 센다."""
    commits = bulk = files = 0
    in_commit = False
    for line in log.splitlines():
        if line.startswith("@@"):
            if in_commit and files >= bulk_threshold:
                bulk += 1
            commits += 1
            files = 0
            in_commit = True
        elif line.strip():
            files += 1
    if in_commit and files >= bulk_threshold:
        bulk += 1
    return commits, bulk


def _branch(repo: Path, cfg: IngestConfig) -> str | None:
    try:
        ref = run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"], cwd=repo,
                      timeout=cfg.clone_timeout_seconds, allow_local=cfg.allow_local_repos).strip()
    except GitError:
        return None
    return ref.removeprefix("origin/") or None
