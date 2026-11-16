package com.codemap.api.common;

/** 계약된 오류 코드로 응답해야 할 때 던진다. {@link GlobalExceptionHandler}가 본문을 만든다. */
public class ApiException extends RuntimeException {

	private final ErrorCode errorCode;

	public ApiException(ErrorCode errorCode) {
		super(errorCode.name());
		this.errorCode = errorCode;
	}

	public ErrorCode getErrorCode() {
		return errorCode;
	}
}
