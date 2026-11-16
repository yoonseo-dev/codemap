package com.codemap.api.common;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest
@AutoConfigureMockMvc
@Import(GlobalExceptionHandlerTest.ThrowingController.class)
class GlobalExceptionHandlerTest {

	@Autowired
	MockMvc mvc;

	@Test
	void apiExceptionUsesContractShape() throws Exception {
		mvc.perform(get("/test-errors/api"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("JOB_NOT_FOUND"))
				.andExpect(jsonPath("$.error.message").value("분석 작업을 찾지 못했어요"));
	}

	@Test
	void hintIsIncludedOnlyWhenPresent() throws Exception {
		mvc.perform(get("/test-errors/repo"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("REPO_NOT_FOUND"))
				.andExpect(jsonPath("$.error.hint").value("공개 저장소의 주소인지 확인해 주세요. 예: github.com/owner/repo"));
		mvc.perform(get("/test-errors/api")).andExpect(jsonPath("$.error.hint").doesNotExist());
	}

	@Test
	void validationFailureIsInvalidRequest() throws Exception {
		mvc.perform(post("/test-errors/body").contentType(MediaType.APPLICATION_JSON).content("{\"repo\":\"\"}"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
	}

	@Test
	void unreadableBodyIsInvalidRequest() throws Exception {
		mvc.perform(post("/test-errors/body").contentType(MediaType.APPLICATION_JSON).content("{not json"))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
	}

	@Test
	void unexpectedExceptionHidesDetails() throws Exception {
		mvc.perform(get("/test-errors/boom"))
				.andExpect(status().isInternalServerError())
				.andExpect(jsonPath("$.error.code").value("INTERNAL"))
				.andExpect(jsonPath("$.error.message").value("잠시 문제가 생겼어요"));
	}

	@Test
	void unknownPathIsNotFound() throws Exception {
		mvc.perform(get("/api/nope"))
				.andExpect(status().isNotFound())
				.andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
	}

	@Test
	void requestsAreNotBlockedBySecurity() throws Exception {
		// 인증을 열어 두었으므로 401/403이 아니라 컨트롤러까지 도달해야 한다
		mvc.perform(post("/test-errors/body").contentType(MediaType.APPLICATION_JSON).content("{\"repo\":\"a/b\"}"))
				.andExpect(status().isOk());
	}

	record Body(@NotBlank String repo) {
	}

	@RestController
	static class ThrowingController {

		@GetMapping("/test-errors/api")
		void api() {
			throw new ApiException(ErrorCode.JOB_NOT_FOUND);
		}

		@GetMapping("/test-errors/repo")
		void repo() {
			throw new ApiException(ErrorCode.REPO_NOT_FOUND);
		}

		@GetMapping("/test-errors/boom")
		void boom() {
			throw new IllegalStateException("비밀 내부 정보");
		}

		@PostMapping("/test-errors/body")
		void body(@Valid @RequestBody Body body) {
		}
	}
}
