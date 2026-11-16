package com.codemap.api.job;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface JobStageRepository extends JpaRepository<JobStage, JobStageId> {

	/** 순서(position)대로 */
	List<JobStage> findByIdJobIdOrderByPosition(Long jobId);

	/** 해당 위치 이후의 단계를 처음 상태(PENDING, 0%)로 되돌린다. */
	@Modifying(clearAutomatically = true, flushAutomatically = true)
	@Query(value = """
			update job_stage
			   set status = 'PENDING', percent = 0, detail = null, metrics = cast('{}' as jsonb), updated_at = now()
			 where job_id = :jobId and position >= :position
			""", nativeQuery = true)
	int resetFrom(@Param("jobId") long jobId, @Param("position") int position);
}
