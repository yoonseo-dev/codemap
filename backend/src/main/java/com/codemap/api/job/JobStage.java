package com.codemap.api.job;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/** 작업 하나의 단계 하나(작업당 5행). 진행 중 갱신은 워커가 psycopg로 직접 쓴다. */
@Entity
@Table(name = "job_stage")
@Getter
@Setter
@NoArgsConstructor
public class JobStage {

	@EmbeddedId
	private JobStageId id;

	/** 순서 0~4 */
	@Column(nullable = false)
	private short position;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false)
	private StageStatus status = StageStatus.PENDING;

	@Column(nullable = false)
	private short percent;

	private String detail;

	@JdbcTypeCode(SqlTypes.JSON)
	@Column(nullable = false)
	private Map<String, Object> metrics = new HashMap<>();

	@UpdateTimestamp
	@Column(nullable = false)
	private Instant updatedAt;

	public JobStage(Long jobId, StageName stage) {
		this.id = new JobStageId(jobId, stage);
		this.position = (short) stage.ordinal();
	}
}
