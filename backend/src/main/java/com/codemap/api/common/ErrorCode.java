package com.codemap.api.common;

import org.springframework.http.HttpStatus;

/**
 * API 오류 코드. 프론트 {@code ErrorCode}(frontend/src/api/types.ts)와 같은 이름을 쓴다.
 * 한국어 문구는 docs/API_CONTRACT.md의 표를 따르고, 표에 없는 코드는 프론트 mock의 문구를 따른다.
 */
public enum ErrorCode {

	INVALID_URL(HttpStatus.BAD_REQUEST, "GitHub 저장소 주소가 아니에요", "예: github.com/owner/repo"),
	REPO_NOT_FOUND(HttpStatus.NOT_FOUND, "이 저장소를 열 수 없어요",
			"공개 저장소의 주소인지 확인해 주세요. 예: github.com/owner/repo"),
	UNSUPPORTED_LANGUAGE(HttpStatus.UNPROCESSABLE_CONTENT, "Java·Python 파일을 찾지 못했어요", null),
	REPO_TOO_LARGE(HttpStatus.CONTENT_TOO_LARGE, "저장소가 너무 커요 (500MB 초과)", null),
	JOB_NOT_FOUND(HttpStatus.NOT_FOUND, "분석 작업을 찾지 못했어요", null),
	JOB_NOT_READY(HttpStatus.CONFLICT, "아직 분석이 끝나지 않았어요", null),
	NOT_RESUMABLE(HttpStatus.CONFLICT, "다시 시도할 수 없는 작업이에요", null),
	INVALID_REQUEST(HttpStatus.BAD_REQUEST, "요청 내용을 확인해 주세요", null),
	NOT_FOUND(HttpStatus.NOT_FOUND, "찾을 수 없어요", null),
	INTERNAL(HttpStatus.INTERNAL_SERVER_ERROR, "잠시 문제가 생겼어요", "잠시 뒤 다시 시도해 주세요");

	private final HttpStatus status;
	private final String message;
	private final String hint;

	ErrorCode(HttpStatus status, String message, String hint) {
		this.status = status;
		this.message = message;
		this.hint = hint;
	}

	public HttpStatus status() {
		return status;
	}

	/** 화면에 그대로 보여줄 수 있는 한국어 문장 */
	public String message() {
		return message;
	}

	/** 해결 방법 안내. 없으면 null */
	public String hint() {
		return hint;
	}
}
