package com.codemap.api.job;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import java.io.Serializable;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Embeddable
@Getter
@EqualsAndHashCode
@NoArgsConstructor
public class JobStageId implements Serializable {

	@Column(name = "job_id")
	private Long jobId;

	@Enumerated(EnumType.STRING)
	private StageName stage;

	public JobStageId(Long jobId, StageName stage) {
		this.jobId = jobId;
		this.stage = stage;
	}
}
