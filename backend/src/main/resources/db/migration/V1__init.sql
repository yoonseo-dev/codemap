-- 초기 스키마 골격. 노드·엣지·임베딩·어긋남 테이블은 Phase 1에서 추가한다.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE repository (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE analysis_job (
    id             BIGSERIAL PRIMARY KEY,
    repository_id  BIGINT      NOT NULL REFERENCES repository (id),
    commit_sha     TEXT,
    status         TEXT        NOT NULL DEFAULT 'QUEUED',  -- QUEUED / RUNNING / DONE / FAILED
    stage          TEXT,                                   -- INGEST / STRUCTURE / SEMANTIC / HISTORY / DIVERGENCE
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ
);
