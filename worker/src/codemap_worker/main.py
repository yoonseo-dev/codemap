"""분석 워커 진입점: RabbitMQ에서 분석 작업을 받아 파이프라인을 실행한다."""

import json
import logging

import pika

from codemap_worker.config import settings

log = logging.getLogger("codemap_worker")


def handle_job(job: dict) -> None:
    # TODO(Phase 1~4): 수집 → 구조 → 의미 → 역사 → 어긋남 탐지 순으로 실행
    log.info("received job: %s", job)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=settings.analysis_queue, durable=True)
    channel.basic_qos(prefetch_count=1)

    def on_message(ch, method, _properties, body):
        handle_job(json.loads(body))
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=settings.analysis_queue, on_message_callback=on_message)
    log.info("waiting for jobs on '%s'", settings.analysis_queue)
    channel.start_consuming()


if __name__ == "__main__":
    main()
