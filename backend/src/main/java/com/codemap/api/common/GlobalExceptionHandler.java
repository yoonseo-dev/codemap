package com.codemap.api.common;

import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

/**
 * 모든 오류를 { "error": { code, message, hint } } 모양으로 바꾼다.
 * Spring MVC가 던지는 표준 예외(본문 파싱 실패, 검증 실패, 없는 주소 등)도 같은 모양이 되도록
 * {@link #handleExceptionInternal}을 덮어쓴다.
 */
@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

	private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

	@ExceptionHandler(ApiException.class)
	ResponseEntity<ApiError> handleApi(ApiException e) {
		return respond(e.getErrorCode());
	}

	@ExceptionHandler(ConstraintViolationException.class)
	ResponseEntity<ApiError> handleConstraintViolation(ConstraintViolationException e) {
		return respond(ErrorCode.INVALID_REQUEST);
	}

	/** 예상 못 한 예외. 화면에는 일반 문구만 보내고 스택은 로그에만 남긴다. */
	@ExceptionHandler(Exception.class)
	ResponseEntity<ApiError> handleUnexpected(Exception e) {
		log.error("처리하지 못한 예외", e);
		return respond(ErrorCode.INTERNAL);
	}

	@Override
	protected ResponseEntity<Object> handleExceptionInternal(Exception ex, Object body, HttpHeaders headers,
			HttpStatusCode statusCode, WebRequest request) {
		ErrorCode code;
		if (statusCode.value() == 404) {
			code = ErrorCode.NOT_FOUND;
		}
		else if (statusCode.is4xxClientError()) {
			code = ErrorCode.INVALID_REQUEST;
		}
		else {
			log.error("Spring MVC 예외", ex);
			code = ErrorCode.INTERNAL;
		}
		return super.handleExceptionInternal(ex, ApiError.of(code), headers, statusCode, request);
	}

	private static ResponseEntity<ApiError> respond(ErrorCode code) {
		return ResponseEntity.status(code.status()).body(ApiError.of(code));
	}
}
