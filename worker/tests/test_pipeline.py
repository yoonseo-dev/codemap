import pytest

from codemap_worker.messages import JobMessage
from codemap_worker.models import STAGES, StageError, StageName, StageStatus
from codemap_worker.pipeline import PipelineConfig, run_job

FAST = PipelineConfig(stage_seconds=0, min_interval=0)


def message(from_stage=None) -> JobMessage:
    return JobMessage.model_validate(
        {"jobId": 7, "repoUrl": "https://github.com/o/r", "commitSha": "a" * 40,
         "fromStage": from_stage}
    )


def run(store, events, config=FAST, from_stage=None, **kw):
    run_job(message(from_stage), store, events, config, sleep=lambda _s: None, **kw)


def stage_events(events):
    return [e for e in events.items if e[0] == "stage"]


def test_success_emits_stages_in_order_then_done_and_saves_graph(store, events):
    run(store, events)

    assert events.items[-1] == ("done",)
    # 단계가 순서대로 시작하고(RUNNING 0%) 끝난다(DONE 100%)
    finished = [e[1] for e in stage_events(events) if e[2] is StageStatus.DONE]
    assert finished == list(STAGES)
    started = [e[1] for e in stage_events(events) if e[2] is StageStatus.RUNNING and e[3] == 0]
    assert started == list(STAGES)
    assert store.job_status == "DONE"
    assert all(v == (StageStatus.DONE, 100) for v in store.stages.values())
    nodes, edges = store.graph
    assert len(nodes) > 100 and edges
    # 그래프를 저장한 뒤에 DONE으로 바꾼다
    kinds = [c[0] for c in store.calls]
    assert kinds.index("graph") < kinds.index("done")


def test_percent_never_goes_backwards_within_a_stage(store, events):
    run(store, events)
    for stage in STAGES:
        percents = [e[3] for e in stage_events(events) if e[1] is stage]
        assert percents == sorted(percents)


def test_failure_marks_stage_failed_and_cancels_the_rest(store, events):
    run(store, events, PipelineConfig(stage_seconds=0, min_interval=0, fail_stage=StageName.SEMANTIC))

    assert store.job_status == "FAILED"
    assert store.stages[StageName.INGEST][0] is StageStatus.DONE
    assert store.stages[StageName.STRUCTURE][0] is StageStatus.DONE
    assert store.stages[StageName.SEMANTIC][0] is StageStatus.FAILED
    assert store.stages[StageName.HISTORY][0] is StageStatus.CANCELLED
    assert store.stages[StageName.DIVERGENCE][0] is StageStatus.CANCELLED
    assert store.graph is None
    # failed 이벤트 직전에 실패한 단계의 FAILED 이벤트가 먼저 나간다 (프론트가 이걸로 단계를 표시한다)
    before_last = events.items[-2]
    assert before_last[:3] == ("stage", StageName.SEMANTIC, StageStatus.FAILED)
    assert 0 < before_last[3] < 100  # 마지막으로 보고된 진행률을 유지한다
    last = events.items[-1]
    assert last[0] == "failed"
    assert last[1].stage is StageName.SEMANTIC and last[1].resumable is True
    assert ("done",) not in events.items


def test_stage_error_keeps_code_message_and_resumable(store, events):
    def boom(ctx, report):
        raise StageError("REPO_TOO_LARGE", "저장소가 너무 커요", resumable=False)

    run(store, events, stage_functions={**_noop_stages(), StageName.INGEST: boom})

    failure = store.failure
    assert (failure.stage, failure.code, failure.resumable) == (
        StageName.INGEST, "REPO_TOO_LARGE", False)
    assert failure.message == "저장소가 너무 커요"


def test_unexpected_exception_in_a_stage_is_internal_and_resumable(store, events):
    def boom(ctx, report):
        raise ZeroDivisionError("x")

    run(store, events, stage_functions={**_noop_stages(), StageName.STRUCTURE: boom})

    assert store.failure.code == "INTERNAL" and store.failure.resumable is True
    assert store.stages[StageName.STRUCTURE][0] is StageStatus.FAILED


def test_retry_from_stage_skips_earlier_stages(store, events):
    ran = []

    def spy(stage):
        return lambda ctx, report: ran.append(stage)

    run(store, events, from_stage="SEMANTIC",
        stage_functions={s: spy(s) for s in STAGES})

    assert ran == [StageName.SEMANTIC, StageName.HISTORY, StageName.DIVERGENCE]
    assert {e[1] for e in stage_events(events)} == set(ran)
    assert store.calls[0] == ("running", 7, StageName.SEMANTIC)
    assert events.items[-1] == ("done",)


def test_missing_or_finished_job_does_nothing(store, events):
    store.running = False

    run(store, events)

    assert events.items == []
    assert store.graph is None


def test_infrastructure_errors_propagate_for_queue_retry(store, events):
    def broken_update(*a, **k):
        raise ConnectionError("db down")

    store.update_stage = broken_update

    with pytest.raises(ConnectionError):
        run(store, events)


def test_progress_writes_are_throttled_but_start_and_finish_are_not(store, events):
    now = [0.0]

    def many_reports(ctx, report):
        for i in range(1, 101):  # 시간이 0.01초씩 흐르는 동안 100번 보고
            now[0] += 0.01
            report(i, f"{i}", {"n": i})

    funcs = {s: many_reports for s in STAGES}
    run_job(message(), store, events, PipelineConfig(stage_seconds=0, min_interval=0.5),
            stage_functions=funcs, clock=lambda: now[0], sleep=lambda _s: None)

    ingest = [e for e in stage_events(events) if e[1] is StageName.INGEST]
    # 시작 1 + 중간(1초 동안 0.5초 간격 → 많아야 2) + 완료 1
    assert ingest[0][2:] == (StageStatus.RUNNING, 0)
    assert ingest[-1][2:] == (StageStatus.DONE, 100)
    assert len(ingest) <= 5
    assert len(ingest) < 100


def _noop_stages():
    return {s: (lambda ctx, report: None) for s in STAGES}
