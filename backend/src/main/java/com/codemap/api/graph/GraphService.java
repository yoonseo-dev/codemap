package com.codemap.api.graph;

import com.codemap.api.analysis.AnalysisJob;
import com.codemap.api.analysis.AnalysisJobRepository;
import com.codemap.api.analysis.JobStatus;
import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import com.codemap.api.common.PublicId;
import com.codemap.api.job.JobStage;
import com.codemap.api.job.JobStageId;
import com.codemap.api.job.JobStageRepository;
import com.codemap.api.job.StageName;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GraphService {

	private final AnalysisJobRepository jobs;
	private final CodeNodeRepository nodes;
	private final CodeEdgeRepository edges;
	private final JobStageRepository stages;

	public GraphService(AnalysisJobRepository jobs, CodeNodeRepository nodes, CodeEdgeRepository edges,
			JobStageRepository stages) {
		this.jobs = jobs;
		this.nodes = nodes;
		this.edges = edges;
		this.stages = stages;
	}

	@Transactional(readOnly = true)
	public GraphResponse get(long jobId) {
		AnalysisJob job = jobs.findById(jobId).orElseThrow(() -> new ApiException(ErrorCode.JOB_NOT_FOUND));
		if (job.getStatus() != JobStatus.DONE) {
			throw new ApiException(ErrorCode.JOB_NOT_READY);
		}
		List<CodeNode> rows = nodes.findByIdJobId(jobId);

		List<GraphResponse.NodeItem> nodeItems = rows.stream().map(n -> new GraphResponse.NodeItem(
				n.getId().getNodeId(), n.getName(), n.getPath(), n.getModuleId(), n.getKind(),
				new int[] { n.getStartLine(), n.getEndLine() }, n.getDegree(), position(n))).toList();

		List<GraphResponse.EdgeItem> edgeItems = edges.findByJobId(jobId).stream()
				.map(e -> new GraphResponse.EdgeItem(e.getSource(), e.getTarget(), e.getKind(), e.getWeight(),
						"cochange".equals(e.getKind()) ? e.getSince() : null))
				.toList();

		return new GraphResponse(PublicId.job(jobId),
				new GraphResponse.Stats(rows.size(), (int) rows.stream().map(CodeNode::getPath).distinct().count(),
						commits(jobId)),
				modules(rows), nodeItems, edgeItems);
	}

	/** module_id로 묶고, 각 묶음에서 degree가 가장 큰 노드를 대표 함수로 한다. 모듈 순서는 id 순. */
	private static List<GraphResponse.ModuleItem> modules(List<CodeNode> rows) {
		Map<String, CodeNode> hub = new LinkedHashMap<>();
		rows.stream().sorted(Comparator.comparing(CodeNode::getModuleId).thenComparing(n -> n.getId().getNodeId()))
				.forEach(n -> hub.merge(n.getModuleId(), n, (a, b) -> b.getDegree() > a.getDegree() ? b : a));
		return hub.entrySet().stream().map(e -> new GraphResponse.ModuleItem(e.getKey(),
				e.getKey().replaceAll("/$", ""), e.getValue().getId().getNodeId())).toList();
	}

	private static float[] position(CodeNode n) {
		return n.getSemX() == null || n.getSemY() == null || n.getSemZ() == null ? null
				: new float[] { n.getSemX(), n.getSemY(), n.getSemZ() };
	}

	/** INGEST 단계 metrics의 commits. 없으면 0 */
	private long commits(long jobId) {
		return stages.findById(new JobStageId(jobId, StageName.INGEST)).map(JobStage::getMetrics)
				.map(m -> m.get("commits")).filter(Number.class::isInstance).map(v -> ((Number) v).longValue())
				.orElse(0L);
	}
}
