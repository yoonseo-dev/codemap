package com.codemap.api.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 인터넷 없이 로컬 저장소로 git ls-remote 연동을 확인한다. */
class GitCliRemoteGitTest {

	private final GitCliRemoteGit git = new GitCliRemoteGit();

	@TempDir
	Path tmp;

	@Test
	void resolvesHeadShaAndBranch() throws Exception {
		Path repo = tmp.resolve("repo");
		Files.createDirectories(repo);
		run(repo, "git", "init", "-q", "-b", "trunk");
		run(repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init");
		String expected = run(repo, "git", "rev-parse", "HEAD").trim();

		RemoteHead head = git.resolveHead(repo.toString());

		assertThat(head.sha()).isEqualTo(expected);
		assertThat(head.branch()).isEqualTo("trunk");
	}

	@Test
	void missingRepositoryIsRepoNotFound() {
		assertThatThrownBy(() -> git.resolveHead(tmp.resolve("does-not-exist").toString()))
				.isInstanceOfSatisfying(ApiException.class,
						e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.REPO_NOT_FOUND));
	}

	@Test
	void emptyRepositoryIsRepoNotFound() throws Exception {
		Path repo = tmp.resolve("empty");
		Files.createDirectories(repo);
		run(repo, "git", "init", "-q");
		// 커밋이 없는 저장소는 HEAD가 없어 분석할 수 없다
		assertThatThrownBy(() -> git.resolveHead(repo.toString())).isInstanceOfSatisfying(ApiException.class,
				e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.REPO_NOT_FOUND));
	}

	@Test
	void parsesSymrefAndSha() {
		RemoteHead head = GitCliRemoteGit.parse(
				"ref: refs/heads/main\tHEAD\na3f9c1e0a3f9c1e0a3f9c1e0a3f9c1e0a3f9c1e0\tHEAD\n");
		assertThat(head).isEqualTo(new RemoteHead("a3f9c1e0a3f9c1e0a3f9c1e0a3f9c1e0a3f9c1e0", "main"));
	}

	private static String run(Path dir, String... command) throws IOException, InterruptedException {
		Process p = new ProcessBuilder(command).directory(dir.toFile()).redirectErrorStream(true).start();
		String out = new String(p.getInputStream().readAllBytes());
		assertThat(p.waitFor(30, TimeUnit.SECONDS)).isTrue();
		assertThat(p.exitValue()).as(out).isZero();
		return out;
	}
}
