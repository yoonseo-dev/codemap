package com.codemap.api.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import com.codemap.api.common.PublicId;
import com.codemap.api.job.JobStage;
import com.codemap.api.job.JobStageRepository;
import com.codemap.api.job.StageName;
import com.codemap.api.job.StageStatus;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/**
 * 서비스 전체 흐름. AFTER_COMMIT 발행을 확인해야 하므로 테스트 트랜잭션을 쓰지 않고 실제로 커밋한 뒤 지운다.
 * 저장소 URL을 테스트마다 유일하게 만들어 다른 데이터와 섞이지 않게 한다.
 */
@SpringBootTest
class AnalysisServiceTest {

	private static final String SHA_1 = "1111111111111111111111111111111111111111";
	private static final String SHA_2 = "2222222222222222222222222222222222222222";

	@Autowired AnalysisService service;
	@Autowired AnalysisJobRepository jobs;
	@Autowired JobStageRepository stages;
	@Autowired SourceRepoRepository repos;
	@Autowired JdbcTemplate jdbc;

	@MockitoBean RemoteGit remoteGit;
	@MockitoBean RabbitTemplate rabbit;

	private final String owner = "t" + UUID.randomUUID().toString().substring(0, 8);
	private final String input = owner + "/service-test";
	private final String url = "https://github.com/" + owner + "/service-test";

	@AfterEach
	void cleanUp() {
		// job_stage는 ON DELETE CASCADE
		jdbc.update("delete from analysis_job where repository_id in (select id from repository where url = ?)", url);
		jdbc.update("delete from repository where url = ?", url);
	}

	@Test
	void newAnalysisCreatesJobAndFiveStagesAndPublishesOnce() {
		when(remoteGit.resolveHead(url)).thenReturn(new RemoteHead(SHA_1, "main"));

		StartAnalysisResponse res = service.start(input);

		assertThat(res.cached()).isFalse();
		assertThat(res.status()).isEqualTo(JobStatus.QUEUED);
		assertThat(res.repository().owner()).isEqualTo(owner);
		assertThat(res.repository().url()).isEqualTo(url);
		long jobId = PublicId.parseJob(res.jobId());

		AnalysisJob job = jobs.findById(jobId).orElseThrow();
		assertThat(job.getCommitSha()).isEqualTo(SHA_1);
		assertThat(job.getBranch()).isEqualTo("main");

		List<JobStage> saved = stages.findByIdJobIdOrderByPosition(jobId);
		assertThat(saved).extracting(s -> s.getId().getStage()).containsExactly(StageName.values());
		assertThat(saved).allSatisfy(s -> {
			assertThat(s.getStatus()).isEqualTo(StageStatus.PENDING);
			assertThat(s.getPercent()).isZero();
		});

		ArgumentCaptor<JobMessage> message = ArgumentCaptor.forClass(JobMessage.class);
		verify(rabbit, times(1)).convertAndSend(eq(""), eq("analysis.jobs"), message.capture());
		assertThat(message.getValue()).isEqualTo(new JobMessage(jobId, url, SHA_1, null));
	}

	@Test
	void pressingTwiceWhileActiveReturnsSameJobWithoutSecondPublish() {
		when(remoteGit.resolveHead(url)).thenReturn(new RemoteHead(SHA_1, "main"));

		StartAnalysisResponse first = service.start(input);
		StartAnalysisResponse second = service.start("https://github.com/" + owner + "/service-test.git");

		assertThat(second.jobId()).isEqualTo(first.jobId());
		assertThat(second.cached()).isFalse();
		verify(rabbit, times(1)).convertAndSend(eq(""), eq("analysis.jobs"), any(JobMessage.class));
		assertThat(jdbc.queryForObject("select count(*) from analysis_job where repository_id = ?", Long.class,
				PublicId.parseRepo(second.repository().id()))).isEqualTo(1L);
	}

	@Test
	void finishedJobForSameCommitIsReturnedAsCached() {
		when(remoteGit.resolveHead(url)).thenReturn(new RemoteHead(SHA_1, "main"));
		StartAnalysisResponse first = service.start(input);
		finish(PublicId.parseJob(first.jobId()));
		Mockito.clearInvocations(rabbit);

		StartAnalysisResponse again = service.start(input);

		assertThat(again.cached()).isTrue();
		assertThat(again.status()).isEqualTo(JobStatus.DONE);
		assertThat(again.jobId()).isEqualTo(first.jobId());
		verify(rabbit, never()).convertAndSend(any(String.class), any(String.class), any(Object.class));
	}

	@Test
	void newCommitCreatesNewJobEvenIfOlderOneIsDone() {
		when(remoteGit.resolveHead(url)).thenReturn(new RemoteHead(SHA_1, "main"));
		StartAnalysisResponse first = service.start(input);
		finish(PublicId.parseJob(first.jobId()));

		when(remoteGit.resolveHead(url)).thenReturn(new RemoteHead(SHA_2, "main"));
		StartAnalysisResponse second = service.start(input);

		assertThat(second.jobId()).isNotEqualTo(first.jobId());
		assertThat(second.cached()).isFalse();
		assertThat(second.repository().id()).isEqualTo(first.repository().id());
		assertThat(repos.findByUrl(url)).isPresent();
	}

	@Test
	void failedJobDoesNotBlockNewAnalysisOfSameCommit() {
		when(remoteGit.resolveHead(url)).thenReturn(new RemoteHead(SHA_1, "main"));
		StartAnalysisResponse first = service.start(input);
		jdbc.update("update analysis_job set status = 'FAILED' where id = ?", PublicId.parseJob(first.jobId()));

		StartAnalysisResponse second = service.start(input);

		assertThat(second.jobId()).isNotEqualTo(first.jobId());
		assertThat(second.cached()).isFalse();
	}

	@Test
	void invalidUrlFailsBeforeAnyNetworkCall() {
		assertThatThrownBy(() -> service.start("not a repo")).isInstanceOfSatisfying(ApiException.class,
				e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.INVALID_URL));
		verify(remoteGit, never()).resolveHead(any());
	}

	@Test
	void unreachableRepositoryCreatesNothing() {
		when(remoteGit.resolveHead(url)).thenThrow(new ApiException(ErrorCode.REPO_NOT_FOUND));

		assertThatThrownBy(() -> service.start(input)).isInstanceOfSatisfying(ApiException.class,
				e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.REPO_NOT_FOUND));

		assertThat(repos.findByUrl(url)).isEmpty();
		verify(rabbit, never()).convertAndSend(any(String.class), any(String.class), any(Object.class));
	}

	private void finish(long jobId) {
		jdbc.update("update analysis_job set status = 'DONE', finished_at = now() where id = ?", jobId);
	}

}
