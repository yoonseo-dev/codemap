package com.codemap.api.analysis;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** {@code git ls-remote --symref <url> HEAD}로 HEAD 커밋과 기본 브랜치를 얻는다. */
@Component
public class GitCliRemoteGit implements RemoteGit {

	private static final Logger log = LoggerFactory.getLogger(GitCliRemoteGit.class);
	private static final Duration TIMEOUT = Duration.ofSeconds(10);
	private static final Pattern SYMREF = Pattern.compile("^ref: refs/heads/(\\S+)\\s+HEAD$");
	private static final Pattern SHA = Pattern.compile("^([0-9a-f]{40}|[0-9a-f]{64})\\s+HEAD$");

	@Override
	public RemoteHead resolveHead(String url) {
		// 비공개 저장소에서 비밀번호를 기다리며 멈추지 않고 바로 실패하게 한다.
		// credential.helper를 비워 Git Credential Manager 같은 대화창도 막는다.
		ProcessBuilder builder = new ProcessBuilder("git", "-c", "credential.helper=", "ls-remote", "--symref", url,
				"HEAD");
		builder.environment().put("GIT_TERMINAL_PROMPT", "0");
		builder.environment().put("GCM_INTERACTIVE", "never");
		builder.redirectError(ProcessBuilder.Redirect.DISCARD);

		Process process = null;
		try {
			process = builder.start();
			process.getOutputStream().close();
			if (!process.waitFor(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS)) {
				log.warn("git ls-remote 시간 초과: {}", url);
				throw notFound();
			}
			if (process.exitValue() != 0) {
				throw notFound();
			}
			String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
			return parse(output);
		}
		catch (IOException e) {
			log.warn("git ls-remote 실행 실패: {}", e.toString());
			throw notFound();
		}
		catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw notFound();
		}
		finally {
			if (process != null && process.isAlive()) {
				process.descendants().forEach(ProcessHandle::destroyForcibly);
				process.destroyForcibly();
			}
		}
	}

	/** ls-remote 출력에서 SHA와 브랜치를 뽑는다. SHA가 없으면(빈 저장소 등) REPO_NOT_FOUND */
	static RemoteHead parse(String output) {
		String sha = null;
		String branch = null;
		for (String line : output.split("\\R")) {
			Matcher symref = SYMREF.matcher(line.trim());
			if (symref.matches()) {
				branch = symref.group(1);
				continue;
			}
			Matcher head = SHA.matcher(line.trim());
			if (head.matches()) {
				sha = head.group(1);
			}
		}
		if (sha == null) {
			throw notFound();
		}
		return new RemoteHead(sha, branch);
	}

	private static ApiException notFound() {
		return new ApiException(ErrorCode.REPO_NOT_FOUND);
	}
}
