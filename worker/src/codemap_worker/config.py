from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수(CODEMAP_*)로 덮어쓸 수 있는 워커 설정."""

    model_config = SettingsConfigDict(env_prefix="CODEMAP_", env_file=".env")

    database_url: str = "postgresql://codemap:codemap@localhost:5442/codemap"
    redis_url: str = "redis://localhost:6389/0"
    rabbitmq_url: str = "amqp://codemap:codemap@localhost:5682/"
    analysis_queue: str = "analysis.jobs"
    workdir: str = "./.repos"

    # 기획서의 초기 설정값
    max_commits: int = 2000
    bulk_commit_file_threshold: int = 50


settings = Settings()
