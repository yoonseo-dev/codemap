package com.codemap.api.analysis;

/** {@code POST /api/analyses} 응답. 같은 커밋을 이미 분석했으면 cached=true, status=DONE */
public record StartAnalysisResponse(String jobId, RepositoryResponse repository, JobStatus status, boolean cached) {
}
