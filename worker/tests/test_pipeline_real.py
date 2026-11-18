"""진짜 INGEST·STRUCTURE와 실제 노드 위의 가짜 SEMANTIC·HISTORY를 이어서 돌린다 (인터넷 없이, 로컬 git 저장소)."""

from pathlib import Path

import pytest
from conftest import FakeEvents, FakeStore
from gitrepo import Repo

from codemap_worker.ingest import IngestConfig
from codemap_worker.messages import JobMessage
from codemap_worker.models import STAGES, StageName, StageStatus
from codemap_worker.pipeline import PipelineConfig, run_job

FIXTURE = Path(__file__).parent / "fixtures" / "py_shop"
EXPECTED_NODES = {
    "billing/invoice.py::InvoiceService.create", "billing/invoice.py::InvoiceService.calc_total",
    "billing/invoice.py::helper", "billing/tax.py::rate_for", "billing/tax.py::lookup",
    "orders/cart.py::sum_items", "orders/cart.py::price", "notify/mailer.py::send",
    "notify/mailer.py::format_message",
}


def source_files() -> dict[str, str]:
    return {p.relative_to(FIXTURE).as_posix(): p.read_text(encoding="utf-8") for p in FIXTURE.rglob("*.py")}


@pytest.fixture
def repo(tmp_path) -> tuple[Repo, str]:
    r = Repo(tmp_path / "shop")
    sha = r.commit(source_files(), "init")
    return r, sha


def config(tmp_path, **kw) -> PipelineConfig:
    return PipelineConfig(stage_seconds=0, min_interval=0, **kw,
                          ingest=IngestConfig(workdir=tmp_path / "work", allow_local_repos=True))


def run(repo, sha, tmp_path, store=None, events=None, from_stage=None, **kw):
    store = store or FakeStore()
    events = events or FakeEvents()
    msg = JobMessage.model_validate({"jobId": 1, "repoUrl": str(repo.path), "commitSha": sha, "fromStage": from_stage})
    run_job(msg, store, events, config(tmp_path, **kw), sleep=lambda _s: None)
    return store, events


def edge_keys(store, kind):
    return sorted((e.source, e.target) for e in store.edges if e.kind == kind)


# ---------- 정상 흐름 ----------

def test_full_run_saves_real_nodes_and_edges_of_all_four_kinds(repo, tmp_path):
    r, sha = repo
    store, events = run(r, sha, tmp_path)

    assert events.items[-1] == ("done",)
    assert store.job_status == "DONE"
    assert {n.id for n in store.nodes} == EXPECTED_NODES
    assert {e.kind for e in store.edges} == {"call", "import", "similar", "cochange"}
    ids = {n.id for n in store.nodes}
    assert all(e.source in ids and e.target in ids for e in store.edges)  # 가짜 엣지도 실제 노드를 가리킨다
    assert set(store.positions) == ids  # 모든 노드가 가짜 의미 좌표를 가진다
    assert all(s is StageStatus.DONE for s, _ in store.stages.values())


def test_stages_run_in_order_and_ingest_fills_commit_info(repo, tmp_path):
    r, sha = repo
    store, events = run(r, sha, tmp_path)

    finished = [d[0] for d in events.stage_details if d[1] is StageStatus.DONE]
    assert finished == list(STAGES)
    branch, date = store.commit_info
    assert branch == "trunk" and date.tzinfo is not None


def test_real_stages_report_real_numbers(repo, tmp_path):
    r, sha = repo
    _, events = run(r, sha, tmp_path)
    done = {d[0]: d for d in events.stage_details if d[1] is StageStatus.DONE}

    ingest = done[StageName.INGEST]
    assert ingest[3] == "커밋 1개를 받고 대량 커밋 0개는 뺐어요"
    assert ingest[4] == {"commits": 1, "bulkExcluded": 0, "sourceFiles": 7}

    structure = done[StageName.STRUCTURE]
    assert structure[3] == "함수 9개, 호출 관계 11개, 해석 성공률 100%"
    assert structure[4]["functions"] == 9 and structure[4]["resolvedRate"] == 1.0
    assert structure[4]["edges"] == 11 and "fake" not in structure[4]

    # 가짜 단계는 임시 값이라는 표시(fake)를 달고, 숫자는 실제 노드 수를 쓴다
    semantic = done[StageName.SEMANTIC]
    assert semantic[4]["fake"] == 1 and semantic[3] == "함수 9개 중 9개 임베딩 (임시 값)"
    assert done[StageName.HISTORY][4]["fake"] == 1
    assert done[StageName.HISTORY][3].endswith("(임시 값)")
    assert done[StageName.DIVERGENCE][4]["fake"] == 1 and done[StageName.DIVERGENCE][3].endswith("(임시 값)")
    # 진짜 단계에는 임시 표시가 없다
    assert "임시" not in done[StageName.INGEST][3] and "임시" not in structure[3]


def test_progress_never_goes_backwards_within_a_stage(repo, tmp_path):
    r, sha = repo
    _, events = run(r, sha, tmp_path)
    for stage in STAGES:
        percents = [d[2] for d in events.stage_details if d[0] is stage]
        assert percents == sorted(percents) and percents[0] == 0 and percents[-1] == 100


def test_running_twice_leaves_the_same_result(repo, tmp_path):
    r, sha = repo
    store, _ = run(r, sha, tmp_path)
    first = (sorted(n.id for n in store.nodes), sorted((e.kind, e.source, e.target) for e in store.edges),
             dict(store.positions))

    run(r, sha, tmp_path, store=store)  # 같은 store에 다시: 메시지가 다시 와도 결과가 같아야 한다

    assert (sorted(n.id for n in store.nodes), sorted((e.kind, e.source, e.target) for e in store.edges),
            dict(store.positions)) == first


# ---------- 실패 ----------

def test_repository_without_sources_fails_in_ingest_and_cannot_be_retried(tmp_path):
    r = Repo(tmp_path / "docs")
    sha = r.commit({"README.md": "hello"})

    store, events = run(r, sha, tmp_path)

    failure = events.items[-1][1]
    assert (failure.stage, failure.code, failure.resumable) == (StageName.INGEST, "UNSUPPORTED_LANGUAGE", False)
    assert store.stages[StageName.INGEST][0] is StageStatus.FAILED
    assert all(store.stages[s][0] is StageStatus.CANCELLED for s in STAGES[1:])
    assert store.job_status == "FAILED" and store.nodes == []


def test_unknown_commit_fails_as_clone_failed_and_can_be_retried(repo, tmp_path):
    r, _ = repo
    _, events = run(r, "f" * 40, tmp_path)
    failure = events.items[-1][1]
    assert (failure.stage, failure.code, failure.resumable) == (StageName.INGEST, "CLONE_FAILED", True)


@pytest.mark.parametrize("stage", [StageName.INGEST, StageName.STRUCTURE, StageName.SEMANTIC, StageName.HISTORY])
def test_fake_fail_stage_works_on_real_and_fake_stages(repo, tmp_path, stage):
    r, sha = repo
    store, events = run(r, sha, tmp_path, fail_stage=stage)

    failure = events.items[-1][1]
    assert (failure.stage, failure.code, failure.resumable) == (stage, "FAKE_FAILURE", True)
    assert store.stages[stage][0] is StageStatus.FAILED
    later = STAGES[STAGES.index(stage) + 1:]
    assert all(store.stages[s][0] is StageStatus.CANCELLED for s in later)
    assert ("done",) not in events.items


def test_failure_in_history_keeps_what_earlier_stages_saved(repo, tmp_path):
    r, sha = repo
    store, _ = run(r, sha, tmp_path, fail_stage=StageName.HISTORY)
    assert {n.id for n in store.nodes} == EXPECTED_NODES
    assert {e.kind for e in store.edges} == {"call", "import", "similar"}  # cochange만 아직 없다


# ---------- 재시도(fromStage) ----------

def test_retry_from_structure_rebuilds_ingest_results_from_the_saved_checkout(repo, tmp_path):
    r, sha = repo
    run(r, sha, tmp_path)  # 작업 폴더를 만들어 둔다
    store, events = run(r, sha, tmp_path, store=FakeStore(), from_stage="STRUCTURE")

    assert [d[0] for d in events.stage_details if d[1] is StageStatus.DONE] == list(STAGES[1:])
    assert {n.id for n in store.nodes} == EXPECTED_NODES
    assert store.commit_info is None  # INGEST를 건너뛰었으니 커밋 정보는 다시 쓰지 않는다
    assert events.items[-1] == ("done",)


def test_retry_from_structure_downloads_again_if_the_checkout_is_gone(repo, tmp_path):
    r, sha = repo
    store, events = run(r, sha, tmp_path, from_stage="STRUCTURE")  # 작업 폴더가 한 번도 없었다
    assert {n.id for n in store.nodes} == EXPECTED_NODES and events.items[-1] == ("done",)


def test_retry_from_semantic_reads_the_saved_graph_and_reproduces_the_fake_results(repo, tmp_path):
    r, sha = repo
    first, _ = run(r, sha, tmp_path)

    # DB에 저장된 상태를 흉내 낸다: 노드·모든 엣지는 있고, 이번에는 SEMANTIC부터만 다시 돌린다
    resumed = FakeStore()
    resumed.nodes, resumed.edges = list(first.nodes), list(first.edges)
    resumed.graph = (resumed.nodes, resumed.edges)
    _, events = run(r, sha, tmp_path, store=resumed, from_stage="SEMANTIC")

    assert [d[0] for d in events.stage_details if d[1] is StageStatus.DONE] == list(STAGES[2:])
    assert ("load_graph",) in resumed.calls and ("graph",) not in resumed.calls  # 구조 결과는 다시 쓰지 않는다
    assert edge_keys(resumed, "call") == edge_keys(first, "call")
    assert edge_keys(resumed, "similar") == edge_keys(first, "similar")  # 같은 입력 → 같은 가짜 결과
    assert edge_keys(resumed, "cochange") == edge_keys(first, "cochange")
    assert resumed.positions == first.positions


def test_retry_from_semantic_without_a_saved_graph_fails_clearly(repo, tmp_path):
    r, sha = repo
    _, events = run(r, sha, tmp_path, from_stage="SEMANTIC")  # 앞 단계 결과가 DB에 없다
    failure = events.items[-1][1]
    assert (failure.stage, failure.code, failure.resumable) == (StageName.SEMANTIC, "INTERNAL", True)
