package com.codemap.api.graph;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/** 지도의 엣지. kind는 call / import / similar / cochange */
@Entity
@Table(name = "code_edge")
@Getter
@Setter
@NoArgsConstructor
public class CodeEdge {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(name = "job_id", nullable = false)
	private Long jobId;

	@Column(nullable = false)
	private String source;

	@Column(nullable = false)
	private String target;

	@Column(nullable = false)
	private String kind;

	@Column(nullable = false)
	private double weight = 1;

	/** cochange 엣지에만 사용 */
	private Instant since;
}
