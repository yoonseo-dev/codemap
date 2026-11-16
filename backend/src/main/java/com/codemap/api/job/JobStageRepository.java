package com.codemap.api.job;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JobStageRepository extends JpaRepository<JobStage, JobStageId> {

	/** 순서(position)대로 */
	List<JobStage> findByIdJobIdOrderByPosition(Long jobId);
}
