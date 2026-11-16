package com.codemap.api.analysis;

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
import org.hibernate.annotations.CreationTimestamp;

/** 분석 대상 저장소(테이블 {@code repository}). Spring Data의 Repository 인터페이스와 이름이 겹쳐 피했다. */
@Entity
@Table(name = "repository")
@Getter
@Setter
@NoArgsConstructor
public class SourceRepo {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(nullable = false, unique = true)
	private String url;

	private String owner;

	private String name;

	private String defaultBranch;

	@CreationTimestamp
	@Column(nullable = false, updatable = false)
	private Instant createdAt;
}
