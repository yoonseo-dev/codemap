"""분석 워커 진입점: RabbitMQ에서 작업을 받아 파이프라인을 실행한다.

큐 3개는 백엔드 AmqpConfig와 **똑같은 인자**로 선언한다. 하나라도 다르면 브로커가
PRECONDITION_FAILED로 연결을 끊는다.

  analysis.jobs        durable, 거절되면 → analysis.jobs.retry
  analysis.jobs.retry  durable, TTL 5초 뒤 → analysis.jobs
  analysis.jobs.dlq    durable, 재시도를 다 쓴 메시지

실패 처리:
  - 분석 실패(StageError 등): DB에 FAILED로 기록하고 ack. 재시도 대상이 아니다.
  - 인프라 오류(DB·Redis 끊김 등): 재시도 횟수가 max_retries 미만이면 nack(requeue=False)로
    retry 큐에 보내 5초 뒤 되돌린다. 다 쓰면 DLQ로 옮기고 ack.
  - 깨진 메시지: 재시도해도 소용없으므로 바로 DLQ.
"""

import json
import logging
import signal
import time
from collections.abc import Callable
from enum import Enum

import pika
import redis
from pika.exceptions import AMQPConnectionError
from pydantic import ValidationError

from codemap_worker.config import Settings, settings
from codemap_worker.events import RedisEventPublisher
from codemap_worker.messages import JobMessage
from codemap_worker.models import StageName
from codemap_worker.pipeline import PipelineConfig, run_job
from codemap_worker.store import PgStore

log = logging.getLogger("codemap_worker")

RECONNECT_DELAY_SECONDS = 5


class Outcome(Enum):
    ACK = "ack"  # 처리 끝(성공이든 분석 실패든)
    RETRY = "retry"  # nack(requeue=False) → retry 큐
    DEAD = "dead"  # DLQ로 옮기고 ack


def process_message(
    body: bytes,
    retry_count: int,
    run: Callable[[JobMessage], None],
    max_retries: int,
) -> Outcome:
    """메시지 하나를 처리하고 브로커에 어떻게 응답할지 돌려준다. 브로커를 모른다."""
    try:
        msg = JobMessage.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        log.exception("깨진 작업 메시지라 DLQ로 보냅니다: %r", body[:200])
        return Outcome.DEAD

    try:
        run(msg)
    except Exception:
        if retry_count < max_retries:
            log.exception("job %s 인프라 오류, 재시도 %d/%d", msg.job_id, retry_count + 1, max_retries)
            return Outcome.RETRY
        log.exception("job %s 재시도를 다 써서 DLQ로 보냅니다", msg.job_id)
        return Outcome.DEAD
    return Outcome.ACK


def retry_count_of(headers: dict | None, queue: str) -> int:
    """x-death에서 이 큐가 거절(rejected)로 retry 큐에 보낸 횟수를 읽는다."""
    for death in (headers or {}).get("x-death", []):
        if death.get("queue") == queue and death.get("reason") == "rejected":
            return int(death.get("count", 0))
    return 0


def declare_queues(channel, cfg: Settings) -> None:
    name = cfg.analysis_queue
    channel.queue_declare(
        queue=name,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": f"{name}.retry"},
    )
    channel.queue_declare(
        queue=f"{name}.retry",
        durable=True,
        arguments={
            "x-message-ttl": cfg.retry_delay_ms,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": name,
        },
    )
    channel.queue_declare(queue=f"{name}.dlq", durable=True)


def build_runner(cfg: Settings) -> Callable[[JobMessage], None]:
    store = PgStore(cfg.database_url)
    events = RedisEventPublisher(
        redis.Redis.from_url(cfg.redis_url), ttl_hours=cfg.event_stream_ttl_hours
    )
    pipeline_config = PipelineConfig(
        stage_seconds=cfg.fake_stage_seconds,
        fail_stage=StageName(cfg.fake_fail_stage) if cfg.fake_fail_stage else None,
        min_interval=cfg.progress_min_interval,
    )
    return lambda msg: run_job(msg, store, events, pipeline_config)


def consume(cfg: Settings, run: Callable[[JobMessage], None]) -> None:
    """연결 하나로 소비한다. 연결이 끊기면 예외로 빠져나가 호출한 쪽이 다시 연결한다."""
    params = pika.URLParameters(cfg.rabbitmq_url)
    # 작업이 길면 BlockingConnection이 heartbeat에 답하지 못해 브로커가 연결을 끊는다.
    # Phase 1은 짧아서 끈다. 실제 분석(Phase 2~)에서는 작업을 별도 스레드로 옮긴다.
    params.heartbeat = 0
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    declare_queues(channel, cfg)
    channel.basic_qos(prefetch_count=1)  # 한 번에 작업 하나

    queue = cfg.analysis_queue

    def on_message(ch, method, properties, body):
        outcome = process_message(body, retry_count_of(properties.headers, queue), run, cfg.max_retries)
        if outcome is Outcome.RETRY:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        if outcome is Outcome.DEAD:
            ch.basic_publish(
                exchange="",
                routing_key=f"{queue}.dlq",
                body=body,
                properties=pika.BasicProperties(delivery_mode=2, headers=properties.headers),
            )
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue, on_message_callback=on_message)
    log.info("waiting for jobs on '%s'", queue)
    try:
        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # docker stop 등의 SIGTERM도 Ctrl+C와 같이 깔끔하게 종료한다.
    def _terminate(*_args):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminate)
    run = build_runner(settings)
    try:
        while True:
            try:
                consume(settings, run)
            except AMQPConnectionError as e:
                log.warning("RabbitMQ 연결이 끊겼어요(%s). %d초 뒤 다시 연결합니다", e, RECONNECT_DELAY_SECONDS)
                time.sleep(RECONNECT_DELAY_SECONDS)
    except KeyboardInterrupt:
        log.info("종료합니다")


if __name__ == "__main__":
    main()
