package com.codemap.api.job;

import com.codemap.api.analysis.AnalysisJob;
import com.codemap.api.analysis.JobStatus;
import com.codemap.api.analysis.RepositoryResponse;
import com.codemap.api.common.PublicId;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** GET /api/jobs/{jobId} 응답. 프론트 {@code Job} 타입과 같은 모양이다. */
public record JobResponse(
		String jobId,
		RepositoryResponse repository,
		CommitResponse commit,
		JobStatus status,
		StageName stage,
		List<StageResponse> stages,
		Instant startedAt,
		Instant finishedAt,
		FailureResponse failure) {

	/** date는 ls-remote로 알 수 없어 지금은 null이다. Phase 2 INGEST에서 워커가 채운다. */
	public record CommitResponse(String sha, String branch, Instant date) {
	}

	public record StageResponse(StageName stage, StageStatus status, int percent, String detail,
			Map<String, Object> metrics) {

		static StageResponse of(JobStage s) {
			return new StageResponse(s.getId().getStage(), s.getStatus(), s.getPercent(), s.getDetail(), s.getMetrics());
		}
	}

	public record FailureResponse(StageName stage, String code, String message, boolean resumable) {
	}

	public static JobResponse of(AnalysisJob job, List<JobStage> stages) {
		return new JobResponse(PublicId.job(job.getId()), RepositoryResponse.of(job.getRepository()), commit(job),
				job.getStatus(), job.getStage(), stages.stream().map(StageResponse::of).toList(),
				job.getStartedAt(), job.getFinishedAt(), failure(job));
	}

	static CommitResponse commit(AnalysisJob job) {
		return job.getCommitSha() == null ? null
				: new CommitResponse(job.getCommitSha(), job.getBranch(), job.getCommitDate());
	}

	static FailureResponse failure(AnalysisJob job) {
		return job.getFailureCode() == null ? null
				: new FailureResponse(job.getFailureStage(), job.getFailureCode(), job.getFailureMessage(),
						Boolean.TRUE.equals(job.getFailureResumable()));
	}
}
