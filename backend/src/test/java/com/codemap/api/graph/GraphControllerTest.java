package com.codemap.api.graph;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.UUID;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class GraphControllerTest {

	@Autowired MockMvc mvc;
	@Autowired JdbcTemplate jdbc;

	private long newJob(String status) {
		String owner = "t" + UUID.randomUUID().toString().substring(0, 8);
		Long repoId = jdbc.queryForObject(
				"insert into repository (url, owner, name) values (?, ?, 'g') returning id", Long.class,
				"https://github.com/" + owner + "/g", owner);
		Long jobId = jdbc.queryForObject(
				"insert into analysis_job (repository_id, commit_sha, status) values (?, 'abc', ?) returning id",
				Long.class, repoId, status);
		jdbc.update("insert into job_stage (job_id, stage, position, status, percent, metrics) "
				+ "values (?, 'INGEST', 0, 'DONE', 100, '{\"commits\": 2000}'::jsonb)", jobId);
		return jobId;
	}

	private void node(long job, String id, String module, int degree, Float sem) {
		jdbc.update("insert into code_node (job_id, node_id, name, path, module_id, kind, start_line, end_line, degree,"
				+ " sem_x, sem_y, sem_z) values (?, ?, ?, ?, ?, 'function', 10, 20, ?, ?, ?, ?)", job, id,
				id.split("::")[1], id.split("::")[0], module, degree, sem, sem, sem);
	}

	private void edge(long job, String s, String t, String kind, double w, boolean since) {
		jdbc.update("insert into code_edge (job_id, source, target, kind, weight, since) values (?, ?, ?, ?, ?, "
				+ (since ? "'2026-01-02T03:04:05Z'" : "null") + ")", job, s, t, kind, w);
	}

	@Test
	void notDoneIs409() throws Exception {
		for (String status : new String[] { "QUEUED", "RUNNING", "FAILED" }) {
			mvc.perform(get("/api/jobs/j_" + newJob(status) + "/graph"))
					.andExpect(status().isConflict())
					.andExpect(jsonPath("$.error.code").value("JOB_NOT_READY"));
		}
	}

	@Test
	void unknownJobIs404() throws Exception {
		mvc.perform(get("/api/jobs/j_999999999/graph"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("JOB_NOT_FOUND"));
	}

	@Test
	void doneJobReturnsContractShape() throws Exception {
		long id = newJob("DONE");
		node(id, "billing/a.py::f", "billing/", 1, 0.5f);
		node(id, "billing/a.py::hub", "billing/", 7, 1.5f);
		node(id, "billing/b.py::g", "billing/", 3, null);
		node(id, "api/r.py::dispatch", "api/", 2, 2f);
		edge(id, "billing/a.py::f", "billing/a.py::hub", "call", 3, false);
		edge(id, "billing/a.py::f", "api/r.py::dispatch", "cochange", 0.8, true);
		edge(id, "billing/a.py::g", "api/r.py::dispatch", "similar", 0.9, true); // similar의 since는 내보내지 않는다

		String body = mvc.perform(get("/api/jobs/j_" + id + "/graph")).andExpect(status().isOk()).andReturn()
				.getResponse().getContentAsString();
		// JsonPath의 [*]·필터가 이 환경에서 null을 돌려줘 응답을 직접 파싱한다
		JsonNode root = JsonMapper.builder().build().readTree(body);

		assertThat(root.get("jobId").asString()).isEqualTo("j_" + id);
		assertThat(root.get("stats").get("functions").asInt()).isEqualTo(4);
		assertThat(root.get("stats").get("files").asInt()).isEqualTo(3);
		assertThat(root.get("stats").get("commits").asInt()).isEqualTo(2000);

		// 모듈은 id 순이고 degree가 가장 큰 노드가 대표 함수
		JsonNode modules = root.get("modules");
		assertThat(modules).hasSize(2);
		assertThat(modules.get(0).get("id").asString()).isEqualTo("api/");
		assertThat(modules.get(0).get("label").asString()).isEqualTo("api");
		assertThat(modules.get(0).get("hubNodeId").asString()).isEqualTo("api/r.py::dispatch");
		assertThat(modules.get(1).get("hubNodeId").asString()).isEqualTo("billing/a.py::hub");

		JsonNode hub = byField(root.get("nodes"), "id", "billing/a.py::hub");
		assertThat(root.get("nodes")).hasSize(4);
		assertThat(hub.get("lines").toString()).isEqualTo("[10,20]");
		assertThat(hub.get("semanticPosition").toString()).isEqualTo("[1.5,1.5,1.5]");
		assertThat(hub.get("moduleId").asString()).isEqualTo("billing/");
		// 의미 좌표가 아직 없는 노드는 null
		assertThat(byField(root.get("nodes"), "id", "billing/b.py::g").get("semanticPosition").isNull()).isTrue();

		JsonNode edges = root.get("edges");
		assertThat(edges).hasSize(3);
		assertThat(byField(edges, "kind", "call").has("since")).isFalse();
		assertThat(byField(edges, "kind", "call").get("weight").asDouble()).isEqualTo(3.0);
		assertThat(byField(edges, "kind", "cochange").get("since").asString()).isEqualTo("2026-01-02T03:04:05Z");
		// similar에 넣어 둔 since는 내보내지 않는다
		assertThat(byField(edges, "kind", "similar").has("since")).isFalse();
	}

	private static JsonNode byField(JsonNode array, String field, String value) {
		for (JsonNode n : array) {
			if (value.equals(n.get(field).asString())) {
				return n;
			}
		}
		throw new AssertionError(field + "=" + value + " 없음");
	}
}
