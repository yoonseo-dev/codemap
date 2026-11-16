package com.codemap.api.graph;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Embeddable
@Getter
@EqualsAndHashCode
@NoArgsConstructor
public class CodeNodeId implements Serializable {

	@Column(name = "job_id")
	private Long jobId;

	/** 파일경로::클래스.함수 */
	@Column(name = "node_id")
	private String nodeId;

	public CodeNodeId(Long jobId, String nodeId) {
		this.jobId = jobId;
		this.nodeId = nodeId;
	}
}
