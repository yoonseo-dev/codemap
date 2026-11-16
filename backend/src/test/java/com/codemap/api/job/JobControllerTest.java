package com.codemap.api.job;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

/** GET /api/jobs/{id} 응답 모양. 테스트 트랜잭션이 롤백되므로 데이터가 남지 않는다. */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class JobControllerTest {

	@Autowired MockMvc mvc;
	@Autowired JdbcTemplate jdbc;

	private long newJob(String status) {
		String owner = "t" + UUID.randomUUID().toString().substring(0, 8);
		Long repoId = jdbc.queryForObject(
				"insert into repository (url, owner, name) values (?, ?, 'demo') returning id", Long.class,
				"https://github.com/" + owner + "/demo", owner);
		Long jobId = jdbc.queryForObject(
				"insert into analysis_job (repository_id, commit_sha, branch, status) values (?, 'abc123', 'main', ?) returning id",
				Long.class, repoId, status);
		String[] names = { "INGEST", "STRUCTURE", "SEMANTIC", "HISTORY", "DIVERGENCE" };
		// 일부러 순서를 뒤섞어 넣어도 position 순으로 나와야 한다
		for (int i = 4; i >= 0; i--) {
			jdbc.update("insert into job_stage (job_id, stage, position) values (?, ?, ?)", jobId, names[i], i);
		}
		return jobId;
	}

	@Test
	void returnsJobInContractShape() throws Exception {
		long id = newJob("QUEUED");

		mvc.perform(get("/api/jobs/j_" + id))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.jobId").value("j_" + id))
				.andExpect(jsonPath("$.repository.name").value("demo"))
				.andExpect(jsonPath("$.repository.id").exists())
				.andExpect(jsonPath("$.commit.sha").value("abc123"))
				.andExpect(jsonPath("$.commit.branch").value("main"))
				.andExpect(jsonPath("$.commit.date").doesNotExist())
				.andExpect(jsonPath("$.status").value("QUEUED"))
				.andExpect(jsonPath("$.stages.length()").value(5))
				.andExpect(jsonPath("$.stages[0].stage").value("INGEST"))
				.andExpect(jsonPath("$.stages[4].stage").value("DIVERGENCE"))
				.andExpect(jsonPath("$.stages[2].status").value("PENDING"))
				.andExpect(jsonPath("$.stages[2].percent").value(0))
				.andExpect(jsonPath("$.stages[2].metrics").isMap())
				.andExpect(jsonPath("$.startedAt").doesNotExist())
				.andExpect(jsonPath("$.failure").doesNotExist());
	}

	@Test
	void nullFieldsArePresentAsNullNotOmitted() throws Exception {
		long id = newJob("QUEUED");

		String body = mvc.perform(get("/api/jobs/j_" + id)).andReturn().getResponse().getContentAsString();

		// 프론트 타입은 commit.date, startedAt, failure를 null로 기대한다 (키가 없으면 undefined가 된다)
		org.assertj.core.api.Assertions.assertThat(body).contains("\"failure\":null", "\"startedAt\":null",
				"\"date\":null");
	}

	@Test
	void failedJobCarriesFailureAndTimestamps() throws Exception {
		long id = newJob("FAILED");
		jdbc.update("update analysis_job set stage='SEMANTIC', started_at = now(), finished_at = now(), "
				+ "failure_stage='SEMANTIC', failure_code='OUT_OF_MEMORY', failure_message='메모리 부족', "
				+ "failure_resumable=true where id=?", id);
		jdbc.update("update job_stage set status='FAILED', percent=64, detail='함수 1,546개', "
				+ "metrics='{\"embedded\":1546}'::jsonb where job_id=? and stage='SEMANTIC'", id);

		mvc.perform(get("/api/jobs/j_" + id))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.status").value("FAILED"))
				.andExpect(jsonPath("$.stage").value("SEMANTIC"))
				.andExpect(jsonPath("$.failure.stage").value("SEMANTIC"))
				.andExpect(jsonPath("$.failure.code").value("OUT_OF_MEMORY"))
				.andExpect(jsonPath("$.failure.message").value("메모리 부족"))
				.andExpect(jsonPath("$.failure.resumable").value(true))
				.andExpect(jsonPath("$.stages[2].status").value("FAILED"))
				.andExpect(jsonPath("$.stages[2].metrics.embedded").value(1546))
				.andExpect(jsonPath("$.startedAt").value(org.hamcrest.Matchers.matchesPattern(
						"\\d{4}-\\d{2}-\\d{2}T.*Z")));
	}

	@Test
	void unknownOrMalformedIdIsJobNotFound() throws Exception {
		for (String id : new String[] { "j_999999999", "abc", "j_", "12" }) {
			mvc.perform(get("/api/jobs/" + id))
					.andExpect(status().isNotFound())
					.andExpect(jsonPath("$.error.code").value("JOB_NOT_FOUND"));
		}
	}
}
