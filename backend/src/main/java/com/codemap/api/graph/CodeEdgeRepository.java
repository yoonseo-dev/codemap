package com.codemap.api.graph;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CodeEdgeRepository extends JpaRepository<CodeEdge, Long> {

	List<CodeEdge> findByJobId(Long jobId);
}
