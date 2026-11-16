package com.codemap.api.analysis;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AnalysisJobRepository extends JpaRepository<AnalysisJob, Long> {

	/** 캐시와 중복 실행 방지용: 같은 저장소·같은 커밋의 작업 중 주어진 상태인 것, 최신순 */
	List<AnalysisJob> findByRepositoryIdAndCommitShaAndStatusInOrderByIdDesc(Long repositoryId, String commitSha,
			Collection<JobStatus> statuses);
}
