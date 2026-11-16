package com.codemap.api.job;

/** 분석 5단계. 선언 순서가 실행 순서(job_stage.position)다. */
public enum StageName {
	INGEST, STRUCTURE, SEMANTIC, HISTORY, DIVERGENCE
}
