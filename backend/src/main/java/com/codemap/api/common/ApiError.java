package com.codemap.api.common;

import com.fasterxml.jackson.annotation.JsonInclude;

/** 4xx·5xx 응답 본문. 프론트 {@code ApiError}와 같은 모양: { "error": { code, message, hint } } */
public record ApiError(Detail error) {

	public record Detail(ErrorCode code, String message, @JsonInclude(JsonInclude.Include.NON_NULL) String hint) {
	}

	public static ApiError of(ErrorCode code) {
		return new ApiError(new Detail(code, code.message(), code.hint()));
	}
}
