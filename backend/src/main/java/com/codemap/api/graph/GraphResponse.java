package com.codemap.api.graph;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;

/** GET /api/jobs/{jobId}/graph 응답. 프론트 {@code Graph} 타입과 같은 모양이다. */
public record GraphResponse(String jobId, Stats stats, List<ModuleItem> modules, List<NodeItem> nodes,
		List<EdgeItem> edges) {

	public record Stats(int functions, int files, long commits) {
	}

	public record ModuleItem(String id, String label, String hubNodeId) {
	}

	public record NodeItem(String id, String name, String path, String moduleId, String kind, int[] lines, int degree,
			float[] semanticPosition) {
	}

	/** since는 cochange에만 있고 나머지 종류에서는 키 자체를 뺀다. */
	public record EdgeItem(String source, String target, String kind, double weight,
			@JsonInclude(JsonInclude.Include.NON_NULL) Instant since) {
	}
}
