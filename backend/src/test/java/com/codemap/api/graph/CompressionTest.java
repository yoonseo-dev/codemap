package com.codemap.api.graph;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;
import java.util.zip.GZIPInputStream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;

/** 큰 지도 응답은 gzip으로 보내고, SSE는 압축하지 않는다. 압축은 서버(Tomcat)가 하므로 실제 서버를 띄워 확인한다. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CompressionTest {

	@LocalServerPort int port;
	@Autowired JdbcTemplate jdbc;

	private final String url = "https://github.com/t" + UUID.randomUUID().toString().substring(0, 8) + "/gz";
	private long jobId;

	@AfterEach
	void cleanUp() {
		jdbc.update("delete from analysis_job where repository_id in (select id from repository where url = ?)", url);
		jdbc.update("delete from repository where url = ?", url);
	}

	private void bigDoneJob() {
		Long repoId = jdbc.queryForObject("insert into repository (url, owner, name) values (?, 'o', 'gz') returning id",
				Long.class, url);
		jobId = jdbc.queryForObject(
				"insert into analysis_job (repository_id, commit_sha, status) values (?, 'abc', 'DONE') returning id",
				Long.class, repoId);
		for (int i = 0; i < 300; i++) {
			jdbc.update("insert into code_node (job_id, node_id, name, path, module_id, kind, start_line, end_line, degree)"
					+ " values (?, ?, ?, 'src/pkg/module.py', 'pkg/', 'function', 1, 9, 0)", jobId,
					"src/pkg/module.py::function_number_" + i, "function_number_" + i);
		}
	}

	private HttpResponse<byte[]> get(String path) throws Exception {
		return HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
				.header("Accept-Encoding", "gzip").build(), HttpResponse.BodyHandlers.ofByteArray());
	}

	@Test
	void graphIsGzippedWhenTheClientAcceptsIt() throws Exception {
		bigDoneJob();

		HttpResponse<byte[]> res = get("/api/jobs/j_" + jobId + "/graph");

		assertThat(res.statusCode()).isEqualTo(200);
		assertThat(res.headers().firstValue("Content-Encoding")).contains("gzip");
		String json = new String(new GZIPInputStream(new ByteArrayInputStream(res.body())).readAllBytes());
		assertThat(json).contains("\"function_number_299\"");
		assertThat(res.body().length).isLessThan(json.length() / 3);
	}

	@Test
	void sseStreamIsNotCompressed() throws Exception {
		bigDoneJob(); // 끝난 작업이라 done 이벤트 하나를 보내고 닫힌다

		HttpResponse<byte[]> res = get("/api/jobs/j_" + jobId + "/events");

		assertThat(res.headers().firstValue("Content-Type").orElse("")).startsWith("text/event-stream");
		assertThat(res.headers().firstValue("Content-Encoding")).isEmpty();
		assertThat(new String(res.body())).contains("event:done");
	}
}
