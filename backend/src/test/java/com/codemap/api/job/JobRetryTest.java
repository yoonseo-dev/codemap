package com.codemap.api.job;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.codemap.api.analysis.JobMessage;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/** 재시도. 발행은 커밋 뒤에 일어나므로 테스트 트랜잭션을 쓰지 않고 실제로 커밋한 뒤 지운다. */
@SpringBootTest
@AutoConfigureMockMvc
class JobRetryTest {

	@Autowired MockMvc mvc;
	@Autowired JdbcTemplate jdbc;
	@Autowired StringRedisTemplate redis;
	@MockitoBean RabbitTemplate rabbit;

	private final String url = "https://github.com/t" + UUID.randomUUID().toString().substring(0, 8) + "/retry";
	private Long jobId;

	@AfterEach
	void cleanUp() {
		if (jobId != null) {
			redis.delete("job:" + jobId + ":events");
		}
		jdbc.update("delete from analysis_job where repository_id in (select id from repository where url = ?)", url);
		jdbc.update("delete from repository where url = ?", url);
	}

	/** SEMANTIC에서 실패한 작업 */
	private long failedJob(boolean resumable) {
		Long repoId = jdbc.queryForObject("insert into repository (url, owner, name) values (?, 'o', 'retry') returning id",
				Long.class, url);
		jobId = jdbc.queryForObject("insert into analysis_job (repository_id, commit_sha, status, stage, started_at,"
				+ " finished_at, failure_stage, failure_code, failure_message, failure_resumable)"
				+ " values (?, 'abc', 'FAILED', 'SEMANTIC', now(), now(), 'SEMANTIC', 'OOM', 'm', ?) returning id",
				Long.class, repoId, resumable);
		String[] names = { "INGEST", "STRUCTURE", "SEMANTIC", "HISTORY", "DIVERGENCE" };
		String[] statuses = { "DONE", "DONE", "FAILED", "CANCELLED", "CANCELLED" };
		for (int i = 0; i < 5; i++) {
			jdbc.update("insert into job_stage (job_id, stage, position, status, percent, detail, metrics)"
					+ " values (?, ?, ?, ?, ?, 'x', '{\"a\":1}'::jsonb)", jobId, names[i], i, statuses[i],
					i < 2 ? 100 : 40);
		}
		return jobId;
	}

	@Test
	void retryResetsFailedAndLaterStagesAndPublishesOnce() throws Exception {
		long id = failedJob(true);
		redis.opsForStream().add(org.springframework.data.redis.connection.stream.StreamRecords
				.string(java.util.Map.of("type", "failed", "data", "{}")).withStreamKey("job:" + id + ":events"));

		mvc.perform(post("/api/jobs/j_" + id + "/retry"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.jobId").value("j_" + id))
				.andExpect(jsonPath("$.status").value("QUEUED"))
				.andExpect(jsonPath("$.failure").doesNotExist())
				.andExpect(jsonPath("$.finishedAt").doesNotExist())
				.andExpect(jsonPath("$.stages[1].status").value("DONE"))
				.andExpect(jsonPath("$.stages[1].percent").value(100))
				.andExpect(jsonPath("$.stages[2].status").value("PENDING"))
				.andExpect(jsonPath("$.stages[2].percent").value(0))
				.andExpect(jsonPath("$.stages[3].status").value("PENDING"))
				.andExpect(jsonPath("$.stages[4].status").value("PENDING"));

		assertThat(jdbc.queryForList("select detail from job_stage where job_id = ? and position >= 2", String.class, id))
				.containsOnlyNulls();
		ArgumentCaptor<JobMessage> msg = ArgumentCaptor.forClass(JobMessage.class);
		verify(rabbit, times(1)).convertAndSend(eq(""), eq("analysis.jobs"), msg.capture());
		assertThat(msg.getValue()).isEqualTo(new JobMessage(id, url, "abc", StageName.SEMANTIC));
		// 이전 실행의 이벤트가 SSE로 먼저 나가지 않도록 스트림을 비운다
		assertThat(redis.hasKey("job:" + id + ":events")).isFalse();
	}

	@Test
	void secondRetryIsRejectedAndDoesNotPublishAgain() throws Exception {
		long id = failedJob(true);

		mvc.perform(post("/api/jobs/j_" + id + "/retry")).andExpect(status().isOk());
		mvc.perform(post("/api/jobs/j_" + id + "/retry"))
				.andExpect(status().isConflict())
				.andExpect(jsonPath("$.error.code").value("NOT_RESUMABLE"));

		verify(rabbit, times(1)).convertAndSend(eq(""), eq("analysis.jobs"), any(JobMessage.class));
	}

	@Test
	void notResumableFailureIsRejected() throws Exception {
		long id = failedJob(false);

		mvc.perform(post("/api/jobs/j_" + id + "/retry"))
				.andExpect(status().isConflict())
				.andExpect(jsonPath("$.error.code").value("NOT_RESUMABLE"));

		verify(rabbit, never()).convertAndSend(any(String.class), any(String.class), any(Object.class));
		assertThat(jdbc.queryForObject("select status from analysis_job where id = ?", String.class, id))
				.isEqualTo("FAILED");
	}

	@Test
	void unknownJobIs404() throws Exception {
		mvc.perform(post("/api/jobs/j_999999999/retry"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("JOB_NOT_FOUND"));
	}
}
