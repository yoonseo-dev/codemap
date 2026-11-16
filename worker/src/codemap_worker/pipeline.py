"""작업 실행기. DB와 Redis를 직접 모르고 `Store`·`EventPublisher`만 받는다.

분석이 실패하면(StageError 등) 실패를 기록하고 정상 반환한다 — 호출한 쪽은 메시지를 ack한다.
DB·Redis 같은 인프라 오류는 잡지 않고 그대로 올려 보낸다. 큐 재시도(main.py)가 맡는다.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from codemap_worker.events import EventPublisher
from codemap_worker.fake_graph import make_fake_graph
from codemap_worker.messages import JobMessage
from codemap_worker.models import STAGES, Failure, StageError, StageName, StageStatus
from codemap_worker.stages import STAGE_FUNCTIONS, StageContext, StageFn
from codemap_worker.store import Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineConfig:
    stage_seconds: float = 1.0
    fail_stage: StageName | None = None
    # 같은 단계 안에서 진행률을 DB·Redis에 쓰는 최소 간격(초). 시작·완료·실패는 항상 바로 쓴다.
    min_interval: float = 0.5


class _Progress:
    """한 단계의 진행률 콜백. 마지막으로 쓴 지 min_interval이 안 지났으면 값만 기억해 둔다."""

    def __init__(self, job_id, stage, store, events, min_interval, clock) -> None:
        self._job_id = job_id
        self._stage = stage
        self._store = store
        self._events = events
        self._min_interval = min_interval
        self._clock = clock
        self._last_write = clock()
        self.percent = 0
        self.detail: str | None = None
        self.metrics: dict[str, float] = {}

    def __call__(self, percent: int, detail: str | None, metrics: dict[str, float]) -> None:
        self.percent, self.detail, self.metrics = percent, detail, metrics
        now = self._clock()
        if now - self._last_write < self._min_interval:
            return
        self._last_write = now
        self._write(StageStatus.RUNNING)

    def _write(self, status: StageStatus) -> None:
        self._store.update_stage(
            self._job_id, self._stage, status, self.percent, self.detail, self.metrics
        )
        self._events.stage(
            self._job_id, self._stage, status, self.percent, self.detail, self.metrics
        )

    def start(self) -> None:
        self._write(StageStatus.RUNNING)

    def finish(self) -> None:
        self.percent = 100
        self._write(StageStatus.DONE)


def run_job(
    msg: JobMessage,
    store: Store,
    events: EventPublisher,
    config: PipelineConfig,
    *,
    stage_functions: dict[StageName, StageFn] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    functions = stage_functions or STAGE_FUNCTIONS
    job_id = msg.job_id

    if not store.mark_job_running(job_id, msg.from_stage):
        log.warning("job %s: 없거나 이미 끝난 작업이라 건너뜁니다", job_id)
        return

    ctx = StageContext(
        job_id=job_id,
        repo_url=msg.repo_url,
        commit_sha=msg.commit_sha,
        stage_seconds=config.stage_seconds,
        fail_stage=config.fail_stage,
        sleep=sleep,
    )
    start = STAGES.index(msg.from_stage) if msg.from_stage else 0

    for stage in STAGES[start:]:
        progress = _Progress(job_id, stage, store, events, config.min_interval, clock)
        progress.start()
        try:
            functions[stage](ctx, progress)
        except StageError as e:
            failure = Failure(stage, e.code, e.message, e.resumable)
        except Exception as e:  # 단계 안의 예상 못 한 오류는 분석 실패로 기록한다
            log.exception("job %s: %s 단계에서 예외", job_id, stage)
            failure = Failure(stage, "INTERNAL", f"{type(e).__name__}: {e}", True)
        else:
            progress.finish()
            continue

        log.warning("job %s failed at %s: %s %s", job_id, stage, failure.code, failure.message)
        store.mark_job_failed(job_id, failure)
        events.failed(job_id, failure)
        return

    nodes, edges = make_fake_graph()
    store.save_graph(job_id, nodes, edges)
    store.mark_job_done(job_id)
    events.done(job_id)
    log.info("job %s done (%d nodes, %d edges)", job_id, len(nodes), len(edges))
