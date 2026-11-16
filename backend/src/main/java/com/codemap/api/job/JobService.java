package com.codemap.api.job;

import com.codemap.api.analysis.AnalysisJob;
import com.codemap.api.analysis.AnalysisJobRepository;
import com.codemap.api.analysis.JobStatus;
import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import com.codemap.api.common.PublicId;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

@Service
public class JobService {

	private final AnalysisJobRepository jobs;
	private final JobStageRepository stages;

	public JobService(AnalysisJobRepository jobs, JobStageRepository stages) {
		this.jobs = jobs;
		this.stages = stages;
	}

	@Transactional(readOnly = true)
	public JobResponse get(long jobId) {
		AnalysisJob job = jobs.findById(jobId).orElseThrow(() -> new ApiException(ErrorCode.JOB_NOT_FOUND));
		return JobResponse.of(job, stages.findByIdJobIdOrderByPosition(jobId));
	}

	@Transactional(readOnly = true)
	public boolean exists(long jobId) {
		return jobs.existsById(jobId);
	}

	/**
	 * 작업이 이미 끝났다면 그 상태를 SSE 이벤트(type, JSON)로 바꿔 돌려준다. 진행 중이면 비어 있다.
	 * Redis 스트림이 만료됐거나, 마지막 이벤트까지 받은 클라이언트가 다시 붙었을 때 쓴다.
	 */
	@Transactional(readOnly = true)
	public Optional<TerminalEvent> terminalEvent(long jobId, JsonMapper json) {
		Optional<AnalysisJob> found = jobs.findById(jobId);
		if (found.isEmpty()) {
			return Optional.empty();
		}
		AnalysisJob job = found.get();
		if (job.getStatus() == JobStatus.DONE) {
			return Optional.of(new TerminalEvent("done",
					json.writeValueAsString(new DonePayload("done", PublicId.job(jobId)))));
		}
		JobResponse.FailureResponse failure = JobResponse.failure(job);
		if (job.getStatus() == JobStatus.FAILED && failure != null) {
			return Optional.of(new TerminalEvent("failed",
					json.writeValueAsString(new FailedPayload("failed", failure))));
		}
		return Optional.empty();
	}

	// 레코드는 선언 순서대로 직렬화되어 워커가 보내는 JSON과 같은 모양이 된다
	record DonePayload(String type, String jobId) {
	}

	record FailedPayload(String type, JobResponse.FailureResponse failure) {
	}

	public record TerminalEvent(String type, String data) {
	}
}
