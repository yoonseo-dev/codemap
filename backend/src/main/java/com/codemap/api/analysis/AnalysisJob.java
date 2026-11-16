package com.codemap.api.analysis;

import com.codemap.api.job.StageName;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "analysis_job")
@Getter
@Setter
@NoArgsConstructor
public class AnalysisJob {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "repository_id")
	private SourceRepo repository;

	private String commitSha;

	private String branch;

	private Instant commitDate;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false)
	private JobStatus status = JobStatus.QUEUED;

	/** 현재 단계. 단계별 상태는 job_stage에 있다. */
	@Enumerated(EnumType.STRING)
	private StageName stage;

	@CreationTimestamp
	@Column(nullable = false, updatable = false)
	private Instant createdAt;

	private Instant startedAt;

	private Instant finishedAt;

	@Enumerated(EnumType.STRING)
	private StageName failureStage;

	private String failureCode;

	private String failureMessage;

	private Boolean failureResumable;
}
