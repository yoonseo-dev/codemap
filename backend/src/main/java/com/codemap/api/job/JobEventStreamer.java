package com.codemap.api.job;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.json.JsonMapper;

/**
 * Redis Stream {@code job:{id}:events}를 SSE로 전달한다. 가상 스레드 하나가 XRANGE를 폴링한다.
 * XREAD BLOCK을 쓰지 않는 이유: 공유 Lettuce 연결에서 BLOCK을 쓰면 다른 Redis 요청까지 막힌다.
 */
@Component
public class JobEventStreamer {

	private static final Logger log = LoggerFactory.getLogger(JobEventStreamer.class);
	static final Duration TIMEOUT = Duration.ofMinutes(30);

	private final StringRedisTemplate redis;
	private final JobService jobs;
	private final JsonMapper json;
	private final long pollMillis;
	private final long pingMillis;

	public JobEventStreamer(StringRedisTemplate redis, JobService jobs, JsonMapper json,
			@Value("${codemap.sse.poll-ms:500}") long pollMillis,
			@Value("${codemap.sse.ping-ms:15000}") long pingMillis) {
		this.redis = redis;
		this.jobs = jobs;
		this.json = json;
		this.pollMillis = pollMillis;
		this.pingMillis = pingMillis;
	}

	public static String streamKey(long jobId) {
		return "job:" + jobId + ":events";
	}

	/** lastEventId 다음 이벤트부터 보낸다. null이면 처음부터. */
	public SseEmitter stream(long jobId, String lastEventId) {
		SseEmitter emitter = new SseEmitter(TIMEOUT.toMillis());
		AtomicBoolean stopped = new AtomicBoolean(false);
		// 클라이언트가 떠나거나 시간이 다 되면 폴링을 멈춘다 (스레드가 새지 않게)
		emitter.onCompletion(() -> stopped.set(true));
		emitter.onTimeout(() -> stopped.set(true));
		emitter.onError(e -> stopped.set(true));
		Thread.ofVirtual().name("sse-job-" + jobId).start(() -> pump(jobId, lastEventId, emitter, stopped));
		return emitter;
	}

	private void pump(long jobId, String lastEventId, SseEmitter emitter, AtomicBoolean stopped) {
		String key = streamKey(jobId);
		String cursor = lastEventId == null || lastEventId.isBlank() ? null : lastEventId.trim();
		long lastSend = System.currentTimeMillis();
		try {
			while (!stopped.get()) {
				List<MapRecord<String, Object, Object>> records = read(key, cursor);
				if (records.isEmpty()) {
					// 새 이벤트가 없는데 작업이 이미 끝났다면(스트림 만료, 끝난 뒤 재접속) 상태로 대신한다.
					// 한 번 더 읽는 이유: DB가 DONE이 된 직후 마지막 이벤트가 막 들어왔을 수 있다.
					Optional<JobService.TerminalEvent> terminal = jobs.terminalEvent(jobId, json);
					if (terminal.isPresent() && read(key, cursor).isEmpty()) {
						emitter.send(SseEmitter.event().name(terminal.get().type()).data(terminal.get().data()));
						emitter.complete();
						return;
					}
				}
				for (MapRecord<String, Object, Object> record : records) {
					String type = String.valueOf(record.getValue().get("type"));
					String data = String.valueOf(record.getValue().get("data"));
					cursor = record.getId().getValue();
					emitter.send(SseEmitter.event().id(cursor).name(type).data(data));
					lastSend = System.currentTimeMillis();
					if (type.equals("done") || type.equals("failed")) {
						emitter.complete();
						return;
					}
				}
				if (System.currentTimeMillis() - lastSend >= pingMillis) {
					emitter.send(SseEmitter.event().comment("ping"));
					lastSend = System.currentTimeMillis();
				}
				Thread.sleep(pollMillis);
			}
		}
		catch (IOException | IllegalStateException e) {
			// 클라이언트가 이미 끊었다
			log.debug("job {} SSE 연결이 끊김: {}", jobId, e.toString());
		}
		catch (InterruptedException e) {
			Thread.currentThread().interrupt();
		}
		catch (RuntimeException e) {
			log.warn("job {} SSE 전달 실패", jobId, e);
			emitter.completeWithError(e);
		}
	}

	/** cursor 뒤의 이벤트. XRANGE는 시작 항목을 포함하므로 cursor와 같은 항목은 건너뛴다. */
	private List<MapRecord<String, Object, Object>> read(String key, String cursor) {
		Range<String> range = cursor == null ? Range.unbounded()
				: Range.rightUnbounded(Range.Bound.inclusive(cursor));
		List<MapRecord<String, Object, Object>> all = redis.opsForStream().range(key, range);
		if (all == null) {
			return List.of();
		}
		return cursor == null ? all : all.stream().filter(r -> !r.getId().getValue().equals(cursor)).toList();
	}
}
