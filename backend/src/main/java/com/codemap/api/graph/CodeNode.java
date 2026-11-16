package com.codemap.api.graph;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/** 지도의 노드(함수·클래스). 계약의 GraphNode와 1:1. 워커가 저장하고 백엔드는 읽기만 한다. */
@Entity
@Table(name = "code_node")
@Getter
@Setter
@NoArgsConstructor
public class CodeNode {

	@EmbeddedId
	private CodeNodeId id;

	@Column(nullable = false)
	private String name;

	@Column(nullable = false)
	private String path;

	@Column(nullable = false)
	private String moduleId;

	@Column(nullable = false)
	private String kind;

	@Column(nullable = false)
	private int startLine;

	@Column(nullable = false)
	private int endLine;

	@Column(nullable = false)
	private int degree;

	/** 의미 모드 UMAP 3D 좌표. 의미 지도 전에는 null */
	@Column(name = "sem_x")
	private Float semX;

	@Column(name = "sem_y")
	private Float semY;

	@Column(name = "sem_z")
	private Float semZ;
}
