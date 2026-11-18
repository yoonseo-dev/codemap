"""DB 저장소(psycopg). 스키마는 백엔드 Flyway가 만들고, 워커는 행만 갱신한다.

모든 함수는 두 번 실행돼도 결과가 같다. RabbitMQ가 같은 메시지를 다시 줄 수 있기 때문이다.
호출마다 연결을 새로 열어 DB가 끊겼다 돌아와도 다음 호출이 그대로 동작한다.
진행률 쓰기는 pipeline이 0.5초에 한 번 이하로 줄여서 부르므로 연결 비용은 무시할 만하다.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from codemap_worker.models import (
    STAGES,
    Failure,
    GraphEdge,
    GraphNode,
    StageName,
    StageStatus,
)


class Store(Protocol):
    def mark_job_running(self, job_id: int, from_stage: StageName | None) -> bool: ...

    def update_stage(
        self,
        job_id: int,
        stage: StageName,
        status: StageStatus,
        percent: int,
        detail: str | None,
        metrics: dict[str, float],
    ) -> None: ...

    def set_commit_info(
        self, job_id: int, branch: str | None, commit_date: datetime | None
    ) -> None: ...

    def save_graph(
        self, job_id: int, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge]
    ) -> None: ...

    def replace_edges(
        self, job_id: int, kinds: Sequence[str], edges: Sequence[GraphEdge]
    ) -> None: ...

    def set_positions(
        self, job_id: int, positions: Mapping[str, tuple[float, float, float]]
    ) -> None: ...

    def load_graph(self, job_id: int) -> tuple[list[GraphNode], list[GraphEdge]]: ...

    def mark_job_done(self, job_id: int) -> None: ...

    def mark_job_failed(self, job_id: int, failure: Failure) -> None: ...


def _position(stage: StageName) -> int:
    return STAGES.index(stage)


class PgStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._url)

    def mark_job_running(self, job_id: int, from_stage: StageName | None) -> bool:
        """RUNNING으로 바꾸고 `from_stage` 이후 단계를 PENDING으로 되돌린다.

        작업이 없거나 이미 DONE이면 False(할 일 없음). 같은 메시지가 다시 와도 이미 끝난 일을
        처음부터 다시 하지 않기 위해서다.
        """
        start = _position(from_stage) if from_stage else 0
        # psycopg3의 with 블록: 정상 종료면 커밋, 예외면 롤백, 어느 쪽이든 연결을 닫는다.
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE analysis_job
                   SET status = 'RUNNING',
                       started_at = COALESCE(started_at, now()),
                       finished_at = NULL,
                       failure_stage = NULL, failure_code = NULL,
                       failure_message = NULL, failure_resumable = NULL
                 WHERE id = %s AND status <> 'DONE'
             RETURNING id
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                """
                UPDATE job_stage
                   SET status = 'PENDING', percent = 0, detail = NULL,
                       metrics = '{}'::jsonb, updated_at = now()
                 WHERE job_id = %s AND position >= %s
                """,
                (job_id, start),
            )
        return True

    def update_stage(self, job_id, stage, status, percent, detail, metrics) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE job_stage
                   SET status = %s, percent = %s, detail = %s, metrics = %s, updated_at = now()
                 WHERE job_id = %s AND stage = %s
                """,
                (status.value, percent, detail, Jsonb(metrics), job_id, stage.value),
            )
            conn.execute("UPDATE analysis_job SET stage = %s WHERE id = %s", (stage.value, job_id))

    def set_commit_info(self, job_id, branch, commit_date) -> None:
        """분석 커밋의 브랜치와 시각. branch를 모르면(None) 기존 값을 그대로 둔다."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE analysis_job SET commit_date = %s, branch = COALESCE(%s, branch) WHERE id = %s",
                (commit_date, branch, job_id),
            )

    def save_graph(self, job_id, nodes, edges) -> None:
        with self._connect() as conn:
            # 같은 작업의 기존 행을 지우고 다시 넣는다 (재실행해도 결과가 같다)
            conn.execute("DELETE FROM code_edge WHERE job_id = %s", (job_id,))
            conn.execute("DELETE FROM code_node WHERE job_id = %s", (job_id,))
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO code_node (job_id, node_id, name, path, module_id, kind,
                                           start_line, end_line, degree, sem_x, sem_y, sem_z)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (job_id, n.id, n.name, n.path, n.module_id, n.kind,
                         n.start_line, n.end_line, n.degree, *(n.sem or (None, None, None)))
                        for n in nodes
                    ],
                )
                cur.executemany(
                    """
                    INSERT INTO code_edge (job_id, source, target, kind, weight, since)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [(job_id, e.source, e.target, e.kind, e.weight, e.since) for e in edges],
                )

    def replace_edges(self, job_id, kinds, edges) -> None:
        """주어진 종류의 엣지만 지우고 다시 넣는다 (다른 종류는 그대로). 두 번 해도 같은 결과."""
        with self._connect() as conn:
            conn.execute("DELETE FROM code_edge WHERE job_id = %s AND kind = ANY(%s)", (job_id, list(kinds)))
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO code_edge (job_id, source, target, kind, weight, since)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [(job_id, e.source, e.target, e.kind, e.weight, e.since) for e in edges],
                )

    def set_positions(self, job_id, positions) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                "UPDATE code_node SET sem_x = %s, sem_y = %s, sem_z = %s WHERE job_id = %s AND node_id = %s",
                [(x, y, z, job_id, node_id) for node_id, (x, y, z) in positions.items()],
            )

    def load_graph(self, job_id):
        """저장된 노드와 구조 엣지(call·import). 재시도로 뒤 단계만 다시 돌릴 때 앞 단계 결과를 읽는다."""
        with self._connect() as conn:
            node_rows = conn.execute(
                """
                SELECT node_id, name, path, module_id, kind, start_line, end_line, degree, sem_x, sem_y, sem_z
                  FROM code_node WHERE job_id = %s ORDER BY node_id
                """,
                (job_id,),
            ).fetchall()
            edge_rows = conn.execute(
                """
                SELECT source, target, kind, weight, since FROM code_edge
                 WHERE job_id = %s AND kind IN ('call', 'import') ORDER BY kind, source, target
                """,
                (job_id,),
            ).fetchall()
        nodes = [
            GraphNode(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                      (r[8], r[9], r[10]) if r[8] is not None else None)
            for r in node_rows
        ]
        edges = [GraphEdge(r[0], r[1], r[2], r[3], r[4]) for r in edge_rows]
        return nodes, edges

    def mark_job_done(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE analysis_job SET status = 'DONE', finished_at = now() WHERE id = %s",
                (job_id,),
            )

    def mark_job_failed(self, job_id: int, failure: Failure) -> None:
        """실패한 단계 FAILED, 뒤 단계 CANCELLED, 작업 FAILED를 한 트랜잭션에서 바꾼다."""
        pos = _position(failure.stage)
        with self._connect() as conn:
            conn.execute(
                "UPDATE job_stage SET status = 'FAILED', updated_at = now() "
                "WHERE job_id = %s AND stage = %s",
                (job_id, failure.stage.value),
            )
            conn.execute(
                """
                UPDATE job_stage
                   SET status = 'CANCELLED', percent = 0, detail = NULL,
                       metrics = '{}'::jsonb, updated_at = now()
                 WHERE job_id = %s AND position > %s
                """,
                (job_id, pos),
            )
            conn.execute(
                """
                UPDATE analysis_job
                   SET status = 'FAILED', stage = %s, finished_at = now(),
                       failure_stage = %s, failure_code = %s,
                       failure_message = %s, failure_resumable = %s
                 WHERE id = %s
                """,
                (
                    failure.stage.value, failure.stage.value, failure.code,
                    failure.message, failure.resumable, job_id,
                ),
            )
