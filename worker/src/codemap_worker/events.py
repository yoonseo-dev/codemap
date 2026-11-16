"""진행률 이벤트 발행. Redis Stream `job:{id}:events`에 쌓고, 백엔드가 SSE로 브라우저에 전달한다.

data는 프론트 `JobEvent`와 같은 모양이다.
  {"type":"stage","stage":{...}} / {"type":"done","jobId":"j_12"} / {"type":"failed","failure":{...}}
"""

import json
from typing import Any, Protocol

from codemap_worker.messages import public_job_id
from codemap_worker.models import Failure, StageName, StageStatus


class EventPublisher(Protocol):
    def stage(
        self,
        job_id: int,
        stage: StageName,
        status: StageStatus,
        percent: int,
        detail: str | None,
        metrics: dict[str, float],
    ) -> None: ...

    def done(self, job_id: int) -> None: ...

    def failed(self, job_id: int, failure: Failure) -> None: ...


def stream_key(job_id: int) -> str:
    return f"job:{job_id}:events"


class RedisEventPublisher:
    MAXLEN = 1000

    def __init__(self, client: Any, ttl_hours: int = 24) -> None:
        self._redis = client
        self._ttl_seconds = ttl_hours * 3600

    def stage(self, job_id, stage, status, percent, detail, metrics) -> None:
        self._add(
            job_id,
            {
                "type": "stage",
                "stage": {
                    "stage": stage.value,
                    "status": status.value,
                    "percent": percent,
                    "detail": detail,
                    "metrics": metrics,
                },
            },
        )

    def done(self, job_id: int) -> None:
        self._add(job_id, {"type": "done", "jobId": public_job_id(job_id)})

    def failed(self, job_id: int, failure: Failure) -> None:
        self._add(job_id, {"type": "failed", "failure": failure.to_json()})

    def _add(self, job_id: int, event: dict) -> None:
        key = stream_key(job_id)
        data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        pipe = self._redis.pipeline()
        pipe.xadd(key, {"type": event["type"], "data": data}, maxlen=self.MAXLEN, approximate=True)
        # 첫 기록 때만 만료를 건다(NX). 오래된 스트림이 Redis에 쌓이지 않게 한다.
        pipe.expire(key, self._ttl_seconds, nx=True)
        pipe.execute()
