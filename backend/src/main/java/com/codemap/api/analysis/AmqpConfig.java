package com.codemap.api.analysis;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 분석 작업 큐 3개. 워커(worker/main.py)도 같은 큐를 선언하므로 인자가 한 글자라도 다르면
 * PRECONDITION_FAILED로 연결이 끊긴다. 여기를 바꾸면 워커도 함께 바꾼다.
 *
 * <pre>
 * analysis.jobs        durable, 거절(nack requeue=false)되면 → analysis.jobs.retry
 * analysis.jobs.retry  durable, TTL 5초 뒤 → analysis.jobs (재시도 대기실)
 * analysis.jobs.dlq    durable, 재시도를 다 쓴 메시지 보관
 * </pre>
 *
 * dead-letter 교환기는 빈 문자열(기본 교환기)이라 routing key가 곧 큐 이름이다.
 */
@Configuration
public class AmqpConfig {

	public static final long RETRY_DELAY_MS = 5_000;

	@Bean
	Queue analysisJobsQueue(@Value("${codemap.analysis-queue}") String name) {
		return QueueBuilder.durable(name).deadLetterExchange("").deadLetterRoutingKey(name + ".retry").build();
	}

	@Bean
	Queue analysisJobsRetryQueue(@Value("${codemap.analysis-queue}") String name) {
		return QueueBuilder.durable(name + ".retry")
				.ttl((int) RETRY_DELAY_MS)
				.deadLetterExchange("")
				.deadLetterRoutingKey(name)
				.build();
	}

	@Bean
	Queue analysisJobsDeadLetterQueue(@Value("${codemap.analysis-queue}") String name) {
		return QueueBuilder.durable(name + ".dlq").build();
	}

	/** 작업 메시지를 JSON으로 보낸다. 워커는 같은 필드의 JSON을 읽는다. */
	@Bean
	MessageConverter jsonMessageConverter() {
		return new JacksonJsonMessageConverter();
	}
}
