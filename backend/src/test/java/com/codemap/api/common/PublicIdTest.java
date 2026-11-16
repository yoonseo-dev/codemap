package com.codemap.api.common;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;

class PublicIdTest {

	@Test
	void roundTrip() {
		assertThat(PublicId.job(12)).isEqualTo("j_12");
		assertThat(PublicId.repo(3)).isEqualTo("r_3");
		assertThat(PublicId.parseJob("j_12")).isEqualTo(12L);
		assertThat(PublicId.parseRepo("r_3")).isEqualTo(3L);
	}

	@ParameterizedTest
	@NullSource
	@ValueSource(strings = { "", "12", "j_", "j_abc", "j_-1", "j_1.5", "r_12", "J_12", " j_12", "j_12 ",
			"j_99999999999999999999" })
	void malformedJobIdIsJobNotFound(String value) {
		assertThatThrownBy(() -> PublicId.parseJob(value)).isInstanceOfSatisfying(ApiException.class,
				e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.JOB_NOT_FOUND));
	}

	@Test
	void malformedRepoIdIsRepoNotFound() {
		assertThatThrownBy(() -> PublicId.parseRepo("j_3")).isInstanceOfSatisfying(ApiException.class,
				e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.REPO_NOT_FOUND));
	}
}
