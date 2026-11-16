package com.codemap.api.analysis;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

/** 요청·응답 모양. 테스트 트랜잭션이 롤백되므로 큐 발행(AFTER_COMMIT)은 일어나지 않는다. */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class AnalysisControllerTest {

	@Autowired MockMvc mvc;

	@MockitoBean RemoteGit remoteGit;
	@MockitoBean RabbitTemplate rabbit;

	@Test
	void startsAnalysisWith201AndContractShape() throws Exception {
		String owner = "t" + UUID.randomUUID().toString().substring(0, 8);
		when(remoteGit.resolveHead("https://github.com/" + owner + "/commerce-core"))
				.thenReturn(new RemoteHead("a3f9c1e0a3f9c1e0a3f9c1e0a3f9c1e0a3f9c1e0", "main"));

		start(owner + "/commerce-core")
				.andExpect(status().isCreated())
				.andExpect(jsonPath("$.jobId").value(org.hamcrest.Matchers.matchesPattern("j_[0-9]+")))
				.andExpect(jsonPath("$.status").value("QUEUED"))
				.andExpect(jsonPath("$.cached").value(false))
				.andExpect(jsonPath("$.repository.id").value(org.hamcrest.Matchers.matchesPattern("r_[0-9]+")))
				.andExpect(jsonPath("$.repository.owner").value(owner))
				.andExpect(jsonPath("$.repository.name").value("commerce-core"))
				.andExpect(jsonPath("$.repository.url").value("https://github.com/" + owner + "/commerce-core"));
	}

	@Test
	void invalidUrlIs400() throws Exception {
		start("gitlab.com/o/r")
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.error.code").value("INVALID_URL"))
				.andExpect(jsonPath("$.error.message").value("GitHub 저장소 주소가 아니에요"));
	}

	@Test
	void unreachableRepositoryIs404() throws Exception {
		when(remoteGit.resolveHead("https://github.com/o/private-repo"))
				.thenThrow(new ApiException(ErrorCode.REPO_NOT_FOUND));

		start("o/private-repo")
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("REPO_NOT_FOUND"))
				.andExpect(jsonPath("$.error.message").value("이 저장소를 열 수 없어요"));
	}

	@Test
	void blankRepoIsInvalidRequest() throws Exception {
		start("   ")
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
	}

	@Test
	void missingRepoFieldIsInvalidRequest() throws Exception {
		mvc.perform(post("/api/analyses").contentType(MediaType.APPLICATION_JSON).content("{}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
	}

	private ResultActions start(String repo) throws Exception {
		return mvc.perform(post("/api/analyses").contentType(MediaType.APPLICATION_JSON)
				.content("{\"repo\":\"" + repo + "\"}"));
	}
}
