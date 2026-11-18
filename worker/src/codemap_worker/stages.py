"""5단계 정의. Phase 2부터 INGEST·STRUCTURE가 진짜이고 나머지는 가짜 구현이다.
가짜 단계(FAKE_STAGE_FUNCTIONS)는 Phase 3·4·5에서 하나씩 진짜 로직으로 바꾼다.

단계 함수 모양: `run(ctx, report)`.
`report(percent, detail, metrics)`는 진행률을 알리는 콜백이다. 얼마나 자주 DB·Redis에 쓸지는
호출하는 쪽(pipeline)이 정하므로 단계 함수는 마음 편히 자주 불러도 된다.
분석 실패는 `StageError`로 알린다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from codemap_worker.ingest import IngestConfig, IngestResult, ingest
from codemap_worker.models import STAGES, StageError, StageName


class Report(Protocol):
    def __call__(self, percent: int, detail: str | None, metrics: dict[str, float]) -> None: ...


@dataclass
class Artifacts:
    """앞 단계가 만든 결과를 뒤 단계에 넘기는 통. 단계 함수가 채운다."""

    ingest: IngestResult | None = None


@dataclass(frozen=True)
class StageContext:
    job_id: int
    repo_url: str
    commit_sha: str
    stage_seconds: float = 1.0
    fail_stage: StageName | None = None
    sleep: Callable[[float], None] = time.sleep
    store: Any = None  # codemap_worker.store.Store (진짜 단계가 결과를 저장할 때 쓴다)
    ingest_config: IngestConfig | None = None
    artifacts: Artifacts = field(default_factory=Artifacts)


StageFn = Callable[[StageContext, Report], None]

_STEPS = 5  # 0→100%를 이 횟수로 나눠 올린다


def _fake(stage: StageName, line: Callable[[float], tuple[str, dict[str, float]]]) -> StageFn:
    """진행률이 `_STEPS`번에 걸쳐 오르는 가짜 단계. line(비율) → (detail, metrics)."""

    def run(ctx: StageContext, report: Report) -> None:
        for i in range(1, _STEPS + 1):
            ctx.sleep(ctx.stage_seconds / _STEPS)
            ratio = i / _STEPS
            if ctx.fail_stage == stage and i == 3:
                # 실패 화면·재시도 확인용. 60% 지점에서 멈춘다.
                raise StageError("FAKE_FAILURE", f"{stage.value} 단계를 일부러 실패시켰어요", True)
            detail, metrics = line(ratio)
            report(int(ratio * 100), detail, metrics)

    return run


def _n(x: float) -> int:
    return round(x)


FAKE_STAGE_FUNCTIONS: dict[StageName, StageFn] = {
    StageName.INGEST: _fake(
        StageName.INGEST,
        lambda r: (
            f"커밋 {_n(2000 * r):,}개를 받고 대량 커밋 {_n(37 * r)}개는 뺐어요",
            {"commits": _n(2000 * r), "bulkExcluded": _n(37 * r)},
        ),
    ),
    StageName.STRUCTURE: _fake(
        StageName.STRUCTURE,
        lambda r: (
            f"함수 {_n(2418 * r):,}개, 호출 관계 {_n(1284 * r):,}개, 해석 성공률 87%",
            {"functions": _n(2418 * r), "edges": _n(1284 * r), "resolvedRate": 0.87},
        ),
    ),
    StageName.SEMANTIC: _fake(
        StageName.SEMANTIC,
        lambda r: (
            f"함수 2,418개 중 {_n(2418 * r):,}개 임베딩",
            {"embedded": _n(2418 * r), "total": 2418},
        ),
    ),
    StageName.HISTORY: _fake(
        StageName.HISTORY,
        lambda r: (
            f"함께 수정된 함수 짝 {_n(312 * r)}개를 찾았어요",
            {"pairs": _n(312 * r)},
        ),
    ),
    StageName.DIVERGENCE: _fake(
        StageName.DIVERGENCE,
        lambda r: (
            f"어긋남 후보 {_n(41 * r)}개를 골랐어요",
            {"candidates": _n(41 * r)},
        ),
    ),
}


def _maybe_fail(ctx: StageContext, stage: StageName, report: Report) -> None:
    """진짜 단계에서도 CODEMAP_FAKE_FAIL_STAGE로 실패 화면을 확인할 수 있게 한다."""
    if ctx.fail_stage == stage:
        report(60, None, {})
        raise StageError("FAKE_FAILURE", f"{stage.value} 단계를 일부러 실패시켰어요", True)


def run_ingest(ctx: StageContext, report: Report) -> None:
    """진짜 수집: clone → 커밋 정보 → 소스 파일. 결과는 artifacts로 넘기고 커밋 시각은 DB에 쓴다."""
    if ctx.ingest_config is None:
        raise StageError("INTERNAL", "수집 설정이 없어요", True)
    result = ingest(ctx.repo_url, ctx.commit_sha, ctx.ingest_config, report)
    ctx.artifacts.ingest = result
    if ctx.store is not None:
        ctx.store.set_commit_info(ctx.job_id, result.commit.branch, result.commit.commit_date)
    _maybe_fail(ctx, StageName.INGEST, report)


# 지금 쓰는 단계 함수. STRUCTURE부터는 아직 가짜다.
STAGE_FUNCTIONS: dict[StageName, StageFn] = {
    **FAKE_STAGE_FUNCTIONS,
    StageName.INGEST: run_ingest,
}

assert set(STAGE_FUNCTIONS) == set(STAGES)
