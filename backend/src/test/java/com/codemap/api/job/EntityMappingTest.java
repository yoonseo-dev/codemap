package com.codemap.api.job;

import static org.assertj.core.api.Assertions.assertThat;

import com.codemap.api.analysis.AnalysisJob;
import com.codemap.api.analysis.AnalysisJobRepository;
import com.codemap.api.analysis.JobStatus;
import com.codemap.api.analysis.SourceRepo;
import com.codemap.api.analysis.SourceRepoRepository;
import com.codemap.api.graph.CodeEdge;
import com.codemap.api.graph.CodeEdgeRepository;
import com.codemap.api.graph.CodeNode;
import com.codemap.api.graph.CodeNodeId;
import com.codemap.api.graph.CodeNodeRepository;
import jakarta.persistence.EntityManager;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

/** 엔티티가 V2 스키마와 실제로 맞물려 저장·조회되는지 본다(ddl-auto=validate는 컬럼 존재만 확인한다). */
@SpringBootTest
@Transactional
class EntityMappingTest {

	@Autowired SourceRepoRepository repos;
	@Autowired AnalysisJobRepository jobs;
	@Autowired JobStageRepository stages;
	@Autowired CodeNodeRepository nodes;
	@Autowired CodeEdgeRepository edges;
	@Autowired EntityManager em;

	@Test
	void jobWithStagesAndGraphRoundTrips() {
		SourceRepo repo = new SourceRepo();
		repo.setUrl("https://github.com/o/mapping-test");
		repo.setOwner("o");
		repo.setName("mapping-test");
		repo.setDefaultBranch("main");
		repos.save(repo);

		AnalysisJob job = new AnalysisJob();
		job.setRepository(repo);
		job.setCommitSha("a3f9c1e");
		job.setBranch("main");
		jobs.save(job);

		for (StageName name : StageName.values()) {
			stages.save(new JobStage(job.getId(), name));
		}
		JobStage semantic = stages.findById(new JobStageId(job.getId(), StageName.SEMANTIC)).orElseThrow();
		semantic.setStatus(StageStatus.RUNNING);
		semantic.setPercent((short) 64);
		semantic.setDetail("함수 2,418개 중 1,546개 임베딩");
		semantic.setMetrics(Map.of("embedded", 1546, "total", 2418));

		CodeNode node = new CodeNode();
		node.setId(new CodeNodeId(job.getId(), "billing/invoice.py::calc_total"));
		node.setName("calc_total");
		node.setPath("billing/invoice.py");
		node.setModuleId("billing/");
		node.setKind("function");
		node.setStartLine(41);
		node.setEndLine(50);
		node.setDegree(7);
		nodes.save(node);

		CodeEdge edge = new CodeEdge();
		edge.setJobId(job.getId());
		edge.setSource("a.py::f");
		edge.setTarget("b.py::g");
		edge.setKind("cochange");
		edge.setWeight(0.71);
		edge.setSince(Instant.parse("2025-06-02T00:00:00Z"));
		edges.save(edge);

		em.flush();
		em.clear();

		AnalysisJob loaded = jobs.findById(job.getId()).orElseThrow();
		assertThat(loaded.getStatus()).isEqualTo(JobStatus.QUEUED);
		assertThat(loaded.getCreatedAt()).isNotNull();
		assertThat(loaded.getRepository().getUrl()).isEqualTo("https://github.com/o/mapping-test");

		List<JobStage> loadedStages = stages.findByIdJobIdOrderByPosition(job.getId());
		assertThat(loadedStages).extracting(s -> s.getId().getStage())
				.containsExactly(StageName.values());
		assertThat(loadedStages).extracting(JobStage::getPosition).containsExactly((short) 0, (short) 1, (short) 2,
				(short) 3, (short) 4);
		JobStage loadedSemantic = loadedStages.get(2);
		assertThat(loadedSemantic.getStatus()).isEqualTo(StageStatus.RUNNING);
		assertThat(loadedSemantic.getPercent()).isEqualTo((short) 64);
		assertThat(loadedSemantic.getMetrics()).containsEntry("embedded", 1546).containsEntry("total", 2418);
		assertThat(loadedStages.get(0).getMetrics()).isEmpty();
		assertThat(loadedStages.get(0).getUpdatedAt()).isNotNull();

		CodeNode loadedNode = nodes.findByIdJobId(job.getId()).getFirst();
		assertThat(loadedNode.getId().getNodeId()).isEqualTo("billing/invoice.py::calc_total");
		assertThat(loadedNode.getSemX()).isNull();

		CodeEdge loadedEdge = edges.findByJobId(job.getId()).getFirst();
		assertThat(loadedEdge.getSince()).isEqualTo(Instant.parse("2025-06-02T00:00:00Z"));
		assertThat(Arrays.asList(loadedEdge.getKind(), loadedEdge.getWeight())).containsExactly("cochange", 0.71);
	}

	@Test
	void sameCommitLookupFindsOnlyMatchingStatuses() {
		SourceRepo repo = new SourceRepo();
		repo.setUrl("https://github.com/o/lookup-test");
		repos.save(repo);

		AnalysisJob done = newJob(repo, "abc", JobStatus.DONE);
		AnalysisJob running = newJob(repo, "abc", JobStatus.RUNNING);
		newJob(repo, "other", JobStatus.DONE);

		assertThat(jobs.findByRepositoryIdAndCommitShaAndStatusInOrderByIdDesc(repo.getId(), "abc",
				List.of(JobStatus.DONE))).containsExactly(done);
		assertThat(jobs.findByRepositoryIdAndCommitShaAndStatusInOrderByIdDesc(repo.getId(), "abc",
				List.of(JobStatus.QUEUED, JobStatus.RUNNING))).containsExactly(running);
	}

	private AnalysisJob newJob(SourceRepo repo, String sha, JobStatus status) {
		AnalysisJob job = new AnalysisJob();
		job.setRepository(repo);
		job.setCommitSha(sha);
		job.setStatus(status);
		return jobs.save(job);
	}
}
