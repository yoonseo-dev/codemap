"""인프라 없이 파이프라인을 돌리기 위한 메모리 안의 가짜 store·events."""

from dataclasses import dataclass, field

import pytest

from codemap_worker.models import STAGES, Failure, StageName, StageStatus


@dataclass
class FakeStore:
    running: bool = True  # False면 작업이 없거나 이미 끝난 것처럼 동작
    calls: list[tuple] = field(default_factory=list)
    stages: dict[StageName, tuple] = field(default_factory=dict)  # stage → (status, percent)
    graph: tuple | None = None
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    positions: dict = field(default_factory=dict)
    job_status: str = "QUEUED"
    failure: Failure | None = None
    commit_info: tuple | None = None

    def mark_job_running(self, job_id, from_stage):
        self.calls.append(("running", job_id, from_stage))
        if not self.running:
            return False
        self.job_status = "RUNNING"
        start = STAGES.index(from_stage) if from_stage else 0
        for s in STAGES[start:]:
            self.stages[s] = (StageStatus.PENDING, 0)
        return True

    def update_stage(self, job_id, stage, status, percent, detail, metrics):
        self.calls.append(("stage", stage, status, percent))
        self.stages[stage] = (status, percent)

    def set_commit_info(self, job_id, branch, commit_date):
        self.calls.append(("commit_info", branch, commit_date))
        self.commit_info = (branch, commit_date)

    def save_graph(self, job_id, nodes, edges):
        """기존 노드·엣지를 모두 교체한다 (PgStore와 같다)."""
        self.calls.append(("graph",))
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.positions = {}
        self.graph = (self.nodes, self.edges)

    def replace_edges(self, job_id, kinds, edges):
        self.calls.append(("replace_edges", tuple(kinds)))
        self.edges = [e for e in self.edges if e.kind not in kinds] + list(edges)
        self.graph = (self.nodes, self.edges)

    def set_positions(self, job_id, positions):
        self.calls.append(("set_positions",))
        self.positions = dict(positions)

    def load_graph(self, job_id):
        self.calls.append(("load_graph",))
        return list(self.nodes), [e for e in self.edges if e.kind in ("call", "import")]

    def mark_job_done(self, job_id):
        self.calls.append(("done",))
        self.job_status = "DONE"

    def mark_job_failed(self, job_id, failure):
        self.calls.append(("failed", failure.stage))
        self.job_status = "FAILED"
        self.failure = failure
        self.stages[failure.stage] = (StageStatus.FAILED, self.stages[failure.stage][1])
        for s in STAGES[STAGES.index(failure.stage) + 1 :]:
            self.stages[s] = (StageStatus.CANCELLED, 0)


@dataclass
class FakeEvents:
    items: list[tuple] = field(default_factory=list)
    stage_details: list[tuple] = field(default_factory=list)  # (stage, status, percent, detail, metrics)

    def stage(self, job_id, stage, status, percent, detail, metrics):
        self.items.append(("stage", stage, status, percent))
        self.stage_details.append((stage, status, percent, detail, dict(metrics)))

    def done(self, job_id):
        self.items.append(("done",))

    def failed(self, job_id, failure):
        self.items.append(("failed", failure))


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def events():
    return FakeEvents()
