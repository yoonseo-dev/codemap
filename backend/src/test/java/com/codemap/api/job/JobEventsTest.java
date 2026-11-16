package com.codemap.api.job;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * SSE 전달. 실제 서버를 띄우고 Redis Stream에 이벤트를 넣어 둔 뒤 HTTP로 읽는다.
 * done/failed를 받으면 서버가 연결을 닫으므로 응답이 끝날 때까지 읽으면 된다.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
		"codemap.sse.poll-ms=50", "codemap.sse.ping-ms=200" })
class JobEventsTest {

	@LocalServerPort int port;
	@Autowired StringRedisTemplate redis;
	@Autowired JdbcTemplate jdbc;

	private final String url = "https://github.com/t" + UUID.randomUUID().toString().substring(0, 8) + "/sse";
	private Long jobId;

	record Sse(String id, String event, String data) {
	}

	private long newJob(String status) {
		Long repoId = jdbc.queryForObject("insert into repository (url, owner, name) values (?, 'o', 'sse') returning id",
				Long.class, url);
		jobId = jdbc.queryForObject(
				"insert into analysis_job (repository_id, commit_sha, status) values (?, 'abc', ?) returning id",
				Long.class, repoId, status);
		return jobId;
	}

	@AfterEach
	void cleanUp() {
		if (jobId != null) {
			redis.delete(JobEventStreamer.streamKey(jobId));
		}
		jdbc.update("delete from analysis_job where repository_id in (select id from repository where url = ?)", url);
		jdbc.update("delete from repository where url = ?", url);
	}

	private String add(long id, String type, String data) {
		return redis.opsForStream().add(
				org.springframework.data.redis.connection.stream.StreamRecords
						.string(Map.of("type", type, "data", data)).withStreamKey(JobEventStreamer.streamKey(id)))
				.getValue();
	}

	private String stageJson(String stage, int percent) {
		return "{\"type\":\"stage\",\"stage\":{\"stage\":\"" + stage + "\",\"status\":\"RUNNING\",\"percent\":" + percent
				+ ",\"detail\":null,\"metrics\":{}}}";
	}

	/** SSE 응답 본문을 이벤트 목록과 주석 줄로 읽는다. */
	private record Result(List<Sse> events, List<String> comments, HttpResponse<?> response) {
	}

	private Result read(String path, String lastEventId) throws Exception {
		HttpRequest.Builder req = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
				.timeout(Duration.ofSeconds(10));
		if (lastEventId != null) {
			req.header("Last-Event-ID", lastEventId);
		}
		HttpResponse<java.util.stream.Stream<String>> res = HttpClient.newHttpClient().send(req.build(),
				HttpResponse.BodyHandlers.ofLines());
		List<Sse> events = new ArrayList<>();
		List<String> comments = new ArrayList<>();
		String id = null, event = null, data = null;
		for (String line : (Iterable<String>) res.body()::iterator) {
			if (line.isEmpty()) {
				if (event != null || data != null) {
					events.add(new Sse(id, event, data));
				}
				id = event = data = null;
			}
			else if (line.startsWith(":")) {
				comments.add(line.substring(1).trim());
			}
			else {
				int i = line.indexOf(':');
				String value = line.substring(i + 1).trim();
				switch (line.substring(0, i)) {
					case "id" -> id = value;
					case "event" -> event = value;
					case "data" -> data = value;
					default -> {
					}
				}
			}
		}
		return new Result(events, comments, res);
	}

	@Test
	void deliversStreamedEventsInOrderAndClosesAfterDone() throws Exception {
		long id = newJob("RUNNING");
		String id1 = add(id, "stage", stageJson("INGEST", 20));
		String id2 = add(id, "stage", stageJson("INGEST", 100));
		String id3 = add(id, "done", "{\"type\":\"done\",\"jobId\":\"j_" + id + "\"}");

		Result r = read("/api/jobs/j_" + id + "/events", null);

		assertThat(r.response().headers().firstValue("Content-Type").orElse("")).startsWith("text/event-stream");
		assertThat(r.response().headers().firstValue("X-Accel-Buffering")).contains("no");
		assertThat(r.events()).extracting(Sse::id).containsExactly(id1, id2, id3);
		assertThat(r.events()).extracting(Sse::event).containsExactly("stage", "stage", "done");
		assertThat(r.events().get(0).data()).isEqualTo(stageJson("INGEST", 20));
		assertThat(r.events().get(2).data()).isEqualTo("{\"type\":\"done\",\"jobId\":\"j_" + id + "\"}");
	}

	@Test
	void lastEventIdSkipsAlreadyDeliveredEvents() throws Exception {
		long id = newJob("RUNNING");
		add(id, "stage", stageJson("INGEST", 20));
		String id2 = add(id, "stage", stageJson("INGEST", 100));
		String id3 = add(id, "failed",
				"{\"type\":\"failed\",\"failure\":{\"stage\":\"STRUCTURE\",\"code\":\"X\",\"message\":\"m\",\"resumable\":true}}");

		Result r = read("/api/jobs/j_" + id + "/events", id2);

		assertThat(r.events()).extracting(Sse::id).containsExactly(id3);
		assertThat(r.events().get(0).event()).isEqualTo("failed");
	}

	@Test
	void eventsAddedWhileConnectedArePushed() throws Exception {
		long id = newJob("RUNNING");
		Thread writer = Thread.ofVirtual().start(() -> {
			try {
				TimeUnit.MILLISECONDS.sleep(300);
				add(id, "stage", stageJson("INGEST", 50));
				TimeUnit.MILLISECONDS.sleep(300);
				add(id, "done", "{\"type\":\"done\",\"jobId\":\"j_" + id + "\"}");
			}
			catch (InterruptedException e) {
				Thread.currentThread().interrupt();
			}
		});

		Result r = read("/api/jobs/j_" + id + "/events", null);
		writer.join();

		assertThat(r.events()).extracting(Sse::event).containsExactly("stage", "done");
		// 이벤트가 없는 동안 연결이 끊기지 않도록 주석 줄을 보낸다
		assertThat(r.comments()).contains("ping");
	}

	@Test
	void finishedJobWithoutStreamGetsSingleDoneEvent() throws Exception {
		long id = newJob("DONE");

		Result r = read("/api/jobs/j_" + id + "/events", null);

		assertThat(r.events()).hasSize(1);
		assertThat(r.events().get(0).event()).isEqualTo("done");
		assertThat(r.events().get(0).data()).isEqualTo("{\"type\":\"done\",\"jobId\":\"j_" + id + "\"}");
	}

	@Test
	void failedJobWithoutStreamGetsSingleFailedEventFromDb() throws Exception {
		long id = newJob("FAILED");
		jdbc.update("update analysis_job set failure_stage='SEMANTIC', failure_code='OOM', failure_message='메모리',"
				+ " failure_resumable=true where id=?", id);

		Result r = read("/api/jobs/j_" + id + "/events", null);

		assertThat(r.events()).hasSize(1);
		assertThat(r.events().get(0).event()).isEqualTo("failed");
		assertThat(r.events().get(0).data()).contains("\"code\":\"OOM\"", "\"resumable\":true", "\"stage\":\"SEMANTIC\"");
	}

	@Test
	void reconnectAfterTerminalEventClosesInsteadOfHanging() throws Exception {
		long id = newJob("DONE");
		add(id, "stage", stageJson("INGEST", 100));
		String doneId = add(id, "done", "{\"type\":\"done\",\"jobId\":\"j_" + id + "\"}");

		Result r = read("/api/jobs/j_" + id + "/events", doneId);

		// 이미 done까지 받았다. 같은 이벤트를 또 주지 않고 상태로 대신한 done 하나만 오고 닫힌다.
		assertThat(r.events()).extracting(Sse::event).containsExactly("done");
	}

	@Test
	void unknownJobIs404() throws Exception {
		HttpResponse<String> res = HttpClient.newHttpClient().send(
				HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/jobs/j_999999999/events")).build(),
				HttpResponse.BodyHandlers.ofString());

		assertThat(res.statusCode()).isEqualTo(404);
		assertThat(res.body()).contains("JOB_NOT_FOUND");
	}
}
