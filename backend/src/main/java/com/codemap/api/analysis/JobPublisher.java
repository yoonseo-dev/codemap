package com.codemap.api.analysis;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 트랜잭션이 커밋된 <b>뒤에</b> 작업을 큐에 발행한다. 커밋 전에 발행하면 워커가 아직 없는 작업 행을 읽을 수 있다.
 * 서비스는 {@code ApplicationEventPublisher.publishEvent(JobMessage)}만 호출하면 된다.
 */
@Component
public class JobPublisher {

	private static final Logger log = LoggerFactory.getLogger(JobPublisher.class);

	private final RabbitTemplate rabbit;
	private final String queue;

	public JobPublisher(RabbitTemplate rabbit, @Value("${codemap.analysis-queue}") String queue) {
		this.rabbit = rabbit;
		this.queue = queue;
	}

	@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
	void onJobQueued(JobMessage message) {
		try {
			rabbit.convertAndSend("", queue, message);
		}
		catch (RuntimeException e) {
			// 작업 행은 이미 커밋되어 QUEUED로 남는다. 발행 실패를 요청 오류로 돌려도 되돌릴 수 없으므로 기록만 한다.
			log.error("작업 {}을 큐에 발행하지 못했습니다", message.jobId(), e);
		}
	}
}
