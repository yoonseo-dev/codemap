import json

from codemap_worker.events import RedisEventPublisher, stream_key
from codemap_worker.main import Outcome, process_message, retry_count_of
from codemap_worker.messages import JobMessage, public_job_id
from codemap_worker.models import Failure, StageName, StageStatus

GOOD = json.dumps(
    {"jobId": 12, "repoUrl": "https://github.com/o/r", "commitSha": "a" * 40, "fromStage": None,
     "__TypeId__": "x"}  # 백엔드가 붙이는 모르는 필드는 무시한다
).encode()


def test_parses_backend_message():
    msg = JobMessage.model_validate(json.loads(GOOD))
    assert (msg.job_id, msg.from_stage) == (12, None)
    retry = JobMessage.model_validate(
        {"jobId": 1, "repoUrl": "u", "commitSha": "s", "fromStage": "SEMANTIC"})
    assert retry.from_stage is StageName.SEMANTIC


def test_success_is_ack():
    assert process_message(GOOD, 0, lambda m: None, 2) is Outcome.ACK


def test_malformed_messages_go_straight_to_dlq_without_running():
    ran = []
    for body in (b"not json", b"{}", b'{"jobId":"x"}', b'{"jobId":1,"repoUrl":"u","commitSha":"s","fromStage":"NOPE"}'):
        assert process_message(body, 0, ran.append, 2) is Outcome.DEAD
    assert ran == []


def test_infra_error_retries_until_limit_then_dead():
    def boom(_msg):
        raise ConnectionError("db down")

    assert process_message(GOOD, 0, boom, 2) is Outcome.RETRY
    assert process_message(GOOD, 1, boom, 2) is Outcome.RETRY
    assert process_message(GOOD, 2, boom, 2) is Outcome.DEAD


def test_retry_count_reads_rejected_deaths_of_the_main_queue():
    headers = {"x-death": [
        {"queue": "analysis.jobs.retry", "reason": "expired", "count": 2},
        {"queue": "analysis.jobs", "reason": "rejected", "count": 2},
    ]}
    assert retry_count_of(headers, "analysis.jobs") == 2
    assert retry_count_of({}, "analysis.jobs") == 0
    assert retry_count_of(None, "analysis.jobs") == 0


class FakePipe:
    def __init__(self, log):
        self.log = log

    def xadd(self, key, fields, maxlen, approximate):
        self.log.append(("xadd", key, fields, maxlen, approximate))

    def expire(self, key, seconds, nx):
        self.log.append(("expire", key, seconds, nx))

    def execute(self):
        self.log.append(("execute",))


class FakeRedis:
    def __init__(self):
        self.log = []

    def pipeline(self):
        return FakePipe(self.log)


def test_redis_events_have_frontend_shape_and_one_shot_ttl():
    r = FakeRedis()
    pub = RedisEventPublisher(r, ttl_hours=24)

    pub.stage(12, StageName.SEMANTIC, StageStatus.RUNNING, 65, "함수 2,418개 중 1,572개 임베딩",
              {"embedded": 1572, "total": 2418})
    pub.done(12)
    pub.failed(12, Failure(StageName.SEMANTIC, "X", "실패", True))

    adds = [e for e in r.log if e[0] == "xadd"]
    assert all(a[1] == stream_key(12) == "job:12:events" for a in adds)
    assert adds[0][3:] == (1000, True)
    first = json.loads(adds[0][2]["data"])
    assert first == {"type": "stage", "stage": {
        "stage": "SEMANTIC", "status": "RUNNING", "percent": 65,
        "detail": "함수 2,418개 중 1,572개 임베딩",
        "metrics": {"embedded": 1572, "total": 2418}}}
    assert adds[0][2]["type"] == "stage"
    assert json.loads(adds[1][2]["data"]) == {"type": "done", "jobId": "j_12"}
    assert json.loads(adds[2][2]["data"]) == {"type": "failed", "failure": {
        "stage": "SEMANTIC", "code": "X", "message": "실패", "resumable": True}}
    expires = [e for e in r.log if e[0] == "expire"]
    assert expires[0] == ("expire", "job:12:events", 24 * 3600, True)


def test_public_job_id_matches_backend_format():
    assert public_job_id(12) == "j_12"
