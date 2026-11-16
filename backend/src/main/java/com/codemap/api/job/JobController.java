package com.codemap.api.job;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import com.codemap.api.common.PublicId;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/jobs")
public class JobController {

	private final JobService service;
	private final JobEventStreamer streamer;

	public JobController(JobService service, JobEventStreamer streamer) {
		this.service = service;
		this.streamer = streamer;
	}

	@GetMapping("/{jobId}")
	public JobResponse get(@PathVariable String jobId) {
		return service.get(PublicId.parseJob(jobId));
	}

	@PostMapping("/{jobId}/retry")
	public JobResponse retry(@PathVariable String jobId) {
		return service.retry(PublicId.parseJob(jobId));
	}

	@GetMapping(value = "/{jobId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
	public ResponseEntity<SseEmitter> events(@PathVariable String jobId,
			@RequestHeader(value = "Last-Event-ID", required = false) String lastEventId) {
		long id = PublicId.parseJob(jobId);
		if (!service.exists(id)) {
			throw new ApiException(ErrorCode.JOB_NOT_FOUND);
		}
		// 프록시가 이벤트를 모아서 보내지 않게 한다
		return ResponseEntity.ok()
				.cacheControl(CacheControl.noCache())
				.header("X-Accel-Buffering", "no")
				.body(streamer.stream(id, lastEventId));
	}
}
