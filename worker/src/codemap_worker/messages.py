"""RabbitMQ 작업 메시지. 백엔드 JobMessage(Java record)와 같은 필드다."""

from pydantic import BaseModel, ConfigDict, Field

from codemap_worker.models import StageName


class JobMessage(BaseModel):
    # 백엔드가 붙이는 __TypeId__ 같은 모르는 필드는 무시한다.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    job_id: int = Field(alias="jobId", gt=0)
    repo_url: str = Field(alias="repoUrl", min_length=1)
    commit_sha: str = Field(alias="commitSha", min_length=1)
    # null이면 처음부터, 값이 있으면 그 단계부터 다시 실행
    from_stage: StageName | None = Field(default=None, alias="fromStage")


def public_job_id(job_id: int) -> str:
    """API의 공개 ID 형식(`j_12`). 백엔드 PublicId.job과 같은 규칙이다."""
    return f"j_{job_id}"
