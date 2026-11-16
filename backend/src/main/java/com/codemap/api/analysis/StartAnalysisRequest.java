package com.codemap.api.analysis;

import jakarta.validation.constraints.NotBlank;

/** {@code POST /api/analyses} 요청. 빈 값이면 INVALID_REQUEST */
public record StartAnalysisRequest(@NotBlank String repo) {
}
