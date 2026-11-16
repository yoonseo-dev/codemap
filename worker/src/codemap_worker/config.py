from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수(CODEMAP_*)로 덮어쓸 수 있는 워커 설정."""

    model_config = SettingsConfigDict(env_prefix="CODEMAP_", env_file=".env")

    database_url: str = "postgresql://codemap:codemap@localhost:5442/codemap"
    redis_url: str = "redis://localhost:6389/0"
    rabbitmq_url: str = "amqp://codemap:codemap@localhost:5682/"
    analysis_queue: str = "analysis.jobs"
    workdir: str = "./.repos"

    # 큐 재시도: x-death 횟수가 이 값에 닿으면 DLQ로 보낸다 (백엔드 AmqpConfig와 맞춘다)
    max_retries: int = 2
    retry_delay_ms: int = 5000

    # Phase 1 가짜 파이프라인
    fake_stage_seconds: float = 1.0  # 가짜 단계 하나에 걸리는 시간. 테스트에서는 0
    fake_fail_stage: str | None = None  # 지정한 단계에서 일부러 실패시킨다 (예: SEMANTIC)
    event_stream_ttl_hours: int = 24
    progress_min_interval: float = 0.5  # 같은 단계 안에서 진행률을 쓰는 최소 간격(초)

    # 기획서의 초기 설정값
    max_commits: int = 2000
    bulk_commit_file_threshold: int = 50


settings = Settings()
