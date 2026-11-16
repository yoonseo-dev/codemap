package com.codemap.api.graph;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CodeNodeRepository extends JpaRepository<CodeNode, CodeNodeId> {

	List<CodeNode> findByIdJobId(Long jobId);
}
