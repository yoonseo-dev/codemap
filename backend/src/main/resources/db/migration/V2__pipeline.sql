-- Phase 1 파이프라인 골격: 작업 단계, 지도 노드·엣지.
-- Flyway는 백엔드가 기동할 때 실행한다. 워커는 스키마를 만들지 않는다.

-- 1-1 repository: 응답의 repository { owner, name, url }과 커밋 정보의 branch에 필요
ALTER TABLE repository
    ADD COLUMN owner          TEXT,
    ADD COLUMN name           TEXT,
    ADD COLUMN default_branch TEXT;

-- 1-2 analysis_job
ALTER TABLE analysis_job
    ADD COLUMN branch             TEXT,
    ADD COLUMN commit_date        TIMESTAMPTZ,
    ADD COLUMN started_at         TIMESTAMPTZ,
    ADD COLUMN failure_stage      TEXT,
    ADD COLUMN failure_code       TEXT,
    ADD COLUMN failure_message    TEXT,
    ADD COLUMN failure_resumable  BOOLEAN,
    ADD CONSTRAINT analysis_job_status_check
        CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED'));

-- 캐시 조회용: 같은 저장소 + 같은 커밋에 끝난 작업이 있는지
CREATE INDEX idx_analysis_job_repo_commit ON analysis_job (repository_id, commit_sha);

-- 1-3 job_stage: 작업당 5행. GET /api/jobs/{id}가 단계 5개의 상태를 배열로 돌려준다.
CREATE TABLE job_stage (
    job_id      BIGINT      NOT NULL REFERENCES analysis_job (id) ON DELETE CASCADE,
    stage       TEXT        NOT NULL,
    position    SMALLINT    NOT NULL,                      -- 순서 0~4
    status      TEXT        NOT NULL DEFAULT 'PENDING',
    percent     SMALLINT    NOT NULL DEFAULT 0,
    detail      TEXT,
    metrics     JSONB       NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, stage),
    CONSTRAINT job_stage_stage_check
        CHECK (stage IN ('INGEST', 'STRUCTURE', 'SEMANTIC', 'HISTORY', 'DIVERGENCE')),
    CONSTRAINT job_stage_status_check
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED', 'CANCELLED')),
    CONSTRAINT job_stage_position_check CHECK (position BETWEEN 0 AND 4),
    CONSTRAINT job_stage_percent_check  CHECK (percent BETWEEN 0 AND 100)
);

-- 1-4 code_node: 계약의 GraphNode 필드와 1:1
CREATE TABLE code_node (
    job_id      BIGINT  NOT NULL REFERENCES analysis_job (id) ON DELETE CASCADE,
    node_id     TEXT    NOT NULL,                          -- 파일경로::클래스.함수
    name        TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    module_id   TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    start_line  INTEGER NOT NULL,
    end_line    INTEGER NOT NULL,
    degree      INTEGER NOT NULL DEFAULT 0,
    sem_x       REAL,
    sem_y       REAL,
    sem_z       REAL,
    PRIMARY KEY (job_id, node_id)
);

-- 1-5 code_edge
-- 모듈 목록(modules)은 테이블을 따로 두지 않고 code_node.module_id로 묶어서 계산한다.
CREATE TABLE code_edge (
    id      BIGSERIAL        PRIMARY KEY,
    job_id  BIGINT           NOT NULL REFERENCES analysis_job (id) ON DELETE CASCADE,
    source  TEXT             NOT NULL,
    target  TEXT             NOT NULL,
    kind    TEXT             NOT NULL,
    weight  DOUBLE PRECISION NOT NULL DEFAULT 1,
    since   TIMESTAMPTZ,                                   -- cochange에만 사용
    CONSTRAINT code_edge_kind_check CHECK (kind IN ('call', 'import', 'similar', 'cochange'))
);

-- Phase 6에서 엣지를 종류별로 나눠 받을 때 쓴다.
CREATE INDEX idx_code_edge_job_kind ON code_edge (job_id, kind);
