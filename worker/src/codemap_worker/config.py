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

    # Phase 2 수집(INGEST)
    clone_timeout_seconds: int = 300  # git 명령 하나가 이 시간을 넘으면 CLONE_TIMEOUT
    max_repo_mb: int = 500  # 작업 폴더가 이 크기를 넘으면 REPO_TOO_LARGE
    max_file_kb: int = 1024  # 이보다 큰 소스 파일은 분석에서 뺀다
    allow_local_repos: bool = False  # 테스트에서만 켠다. 운영은 https://github.com/ 주소만 받는다


settings = Settings()
