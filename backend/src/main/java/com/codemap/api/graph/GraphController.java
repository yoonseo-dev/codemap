package com.codemap.api.graph;

import com.codemap.api.common.PublicId;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/jobs")
public class GraphController {

	private final GraphService service;

	public GraphController(GraphService service) {
		this.service = service;
	}

	@GetMapping("/{jobId}/graph")
	public GraphResponse graph(@PathVariable String jobId) {
		return service.get(PublicId.parseJob(jobId));
	}
}
