"""파이프라인 전반에서 쓰는 값 객체. DB·Redis·RabbitMQ를 모른다."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class StageName(StrEnum):
    INGEST = "INGEST"
    STRUCTURE = "STRUCTURE"
    SEMANTIC = "SEMANTIC"
    HISTORY = "HISTORY"
    DIVERGENCE = "DIVERGENCE"


# 실행 순서. 백엔드 StageName enum, job_stage.position(0~4)과 같다.
STAGES: tuple[StageName, ...] = tuple(StageName)


class StageStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageError(Exception):
    """단계 함수가 분석 실패를 알릴 때 던진다. 재시도 대상이 아니라 FAILED로 기록되는 실패다."""

    def __init__(self, code: str, message: str, resumable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.resumable = resumable


@dataclass(frozen=True)
class Failure:
    """프론트 JobFailure와 같은 모양."""

    stage: StageName
    code: str
    message: str
    resumable: bool

    def to_json(self) -> dict:
        return {
            "stage": self.stage.value,
            "code": self.code,
            "message": self.message,
            "resumable": self.resumable,
        }


@dataclass(frozen=True)
class GraphNode:
    id: str
    name: str
    path: str
    module_id: str
    kind: str  # function | method
    start_line: int
    end_line: int
    degree: int
    sem: tuple[float, float, float] | None = None  # 의미 좌표. 의미 지도 전에는 없다


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str  # call | import | similar | cochange
    weight: float
    since: datetime | None = None  # cochange만
