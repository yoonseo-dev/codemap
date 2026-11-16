package com.codemap.api.analysis;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AnalysisJobRepository extends JpaRepository<AnalysisJob, Long> {

	/** 캐시와 중복 실행 방지용: 같은 저장소·같은 커밋의 작업 중 주어진 상태인 것, 최신순 */
	List<AnalysisJob> findByRepositoryIdAndCommitShaAndStatusInOrderByIdDesc(Long repositoryId, String commitSha,
			Collection<JobStatus> statuses);

	/**
	 * 실패한(재시도 가능한) 작업을 QUEUED로 되돌린다. 영향받은 행이 0이면 다른 요청이 먼저 처리했거나 조건이 안 맞는 것이다.
	 * 버튼을 두 번 눌러도 한 번만 성공하게 하는 장치다.
	 */
	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query("""
			update AnalysisJob j
			   set j.status = com.codemap.api.analysis.JobStatus.QUEUED, j.finishedAt = null,
			       j.failureStage = null, j.failureCode = null, j.failureMessage = null, j.failureResumable = null
			 where j.id = :id and j.status = com.codemap.api.analysis.JobStatus.FAILED and j.failureResumable = true
			""")
	int requeueFailed(@Param("id") long id);
}
