package com.codemap.api.analysis;

import com.codemap.api.common.PublicId;
import com.codemap.api.job.JobStage;
import com.codemap.api.job.JobStageRepository;
import com.codemap.api.job.StageName;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class AnalysisService {

	private final RemoteGit remoteGit;
	private final SourceRepoRepository repos;
	private final AnalysisJobRepository jobs;
	private final JobStageRepository stages;
	private final ApplicationEventPublisher events;
	private final TransactionTemplate tx;

	public AnalysisService(RemoteGit remoteGit, SourceRepoRepository repos, AnalysisJobRepository jobs,
			JobStageRepository stages, ApplicationEventPublisher events,
			PlatformTransactionManager txManager) {
		this.remoteGit = remoteGit;
		this.repos = repos;
		this.jobs = jobs;
		this.stages = stages;
		this.events = events;
		this.tx = new TransactionTemplate(txManager);
	}

	/**
	 * 저장소 주소를 받아 분석 작업을 시작한다.
	 * <ol>
	 *   <li>주소 해석과 HEAD 확인: 네트워크 호출이라 트랜잭션 밖에서 한다.</li>
	 *   <li>같은 저장소·같은 커밋으로 끝난 작업이 있으면 그것을 돌려준다(cached).</li>
	 *   <li>진행 중인 작업이 있으면 그것을 돌려준다. 두 번 눌러도 작업이 둘 생기지 않는다.</li>
	 *   <li>아니면 작업(QUEUED)과 단계 5행을 만들고, 커밋 뒤에 큐에 발행한다.</li>
	 * </ol>
	 */
	public StartAnalysisResponse start(String input) {
		ParsedRepo parsed = RepoUrlParser.parse(input);
		RemoteHead head = remoteGit.resolveHead(parsed.url());
		try {
			return inTransaction(parsed, head);
		}
		catch (DataIntegrityViolationException e) {
			// 같은 URL의 저장소를 동시에 만들려던 요청과 겹침. 이제 행이 있으므로 한 번 더 시도한다.
			return inTransaction(parsed, head);
		}
	}

	private StartAnalysisResponse inTransaction(ParsedRepo parsed, RemoteHead head) {
		return Objects.requireNonNull(tx.execute(status -> startInTransaction(parsed, head)));
	}

	private StartAnalysisResponse startInTransaction(ParsedRepo parsed, RemoteHead head) {
		SourceRepo repo = repos.findByUrl(parsed.url())
				.map(existing -> repos.findByIdForUpdate(existing.getId()).orElseThrow())
				.orElseGet(() -> createRepo(parsed));
		if (repo.getOwner() == null) {
			repo.setOwner(parsed.owner());
		}
		if (repo.getName() == null) {
			repo.setName(parsed.name());
		}
		if (head.branch() != null) {
			repo.setDefaultBranch(head.branch());
		}

		var done = jobs.findByRepositoryIdAndCommitShaAndStatusInOrderByIdDesc(repo.getId(), head.sha(),
				List.of(JobStatus.DONE));
		if (!done.isEmpty()) {
			return response(done.getFirst(), repo, true);
		}
		var active = jobs.findByRepositoryIdAndCommitShaAndStatusInOrderByIdDesc(repo.getId(), head.sha(),
				List.of(JobStatus.QUEUED, JobStatus.RUNNING));
		if (!active.isEmpty()) {
			return response(active.getFirst(), repo, false);
		}

		AnalysisJob job = new AnalysisJob();
		job.setRepository(repo);
		job.setCommitSha(head.sha());
		job.setBranch(head.branch());
		jobs.save(job);
		stages.saveAll(Arrays.stream(StageName.values()).map(name -> new JobStage(job.getId(), name)).toList());

		events.publishEvent(new JobMessage(job.getId(), repo.getUrl(), head.sha(), null));
		return response(job, repo, false);
	}

	private SourceRepo createRepo(ParsedRepo parsed) {
		SourceRepo repo = new SourceRepo();
		repo.setUrl(parsed.url());
		repo.setOwner(parsed.owner());
		repo.setName(parsed.name());
		// 유니크 위반을 이 시점에 드러내려고 바로 반영한다
		return repos.saveAndFlush(repo);
	}

	private static StartAnalysisResponse response(AnalysisJob job, SourceRepo repo, boolean cached) {
		return new StartAnalysisResponse(PublicId.job(job.getId()), RepositoryResponse.of(repo), job.getStatus(),
				cached);
	}
}
