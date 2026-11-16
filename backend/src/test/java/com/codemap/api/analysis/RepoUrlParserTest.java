package com.codemap.api.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class RepoUrlParserTest {

	@ParameterizedTest(name = "[{index}] {0}")
	@CsvSource({
			"sample-store/commerce-core,                          sample-store, commerce-core",
			"github.com/sample-store/commerce-core,               sample-store, commerce-core",
			"https://github.com/sample-store/commerce-core,       sample-store, commerce-core",
			"http://github.com/sample-store/commerce-core,        sample-store, commerce-core",
			"https://www.github.com/sample-store/commerce-core,   sample-store, commerce-core",
			"https://github.com/sample-store/commerce-core.git,   sample-store, commerce-core",
			"https://github.com/sample-store/commerce-core/,      sample-store, commerce-core",
			"https://github.com/sample-store/commerce-core.git/,  sample-store, commerce-core",
			"'  github.com/sample-store/commerce-core  ',         sample-store, commerce-core",
			"HTTPS://GitHub.com/Spring-Projects/spring.boot,      Spring-Projects, spring.boot",
			"o/r_with-dots.and_more,                              o, r_with-dots.and_more" })
	void parsesAcceptedForms(String input, String owner, String name) {
		ParsedRepo parsed = RepoUrlParser.parse(input);
		assertThat(parsed.owner()).isEqualTo(owner);
		assertThat(parsed.name()).isEqualTo(name);
		assertThat(parsed.url()).isEqualTo("https://github.com/" + owner + "/" + name);
	}

	@ParameterizedTest(name = "[{index}] \"{0}\"")
	@NullAndEmptySource
	@ValueSource(strings = {
			"   ",
			"commerce-core",                                   // 경로 부족
			"github.com/sample-store",                         // 경로 부족
			"https://github.com/",                             // 경로 없음
			"https://gitlab.com/sample-store/commerce-core",   // 다른 호스트
			"https://o/r",                                     // 스킴이 있는데 호스트가 GitHub가 아님
			"gitlab.com/sample-store/commerce-core",           // owner에 점
			"a/b/c",                                           // 경로 초과
			"https://github.com/o/r/tree/main",                // 경로 초과
			"https://github.com/o/r?tab=readme",               // 쿼리
			"-bad/repo",                                       // owner가 하이픈으로 시작
			"o/..",                                            // 상위 디렉터리
			"o/.",
			"o/.git",                                          // 이름이 비었음
			"o/--upload-pack=evil",                            // git 옵션처럼 보이는 입력
			"o/r name",                                        // 공백
			"git@github.com:o/r.git",                          // ssh 형식
			"file:///etc/passwd" })
	void rejectsEverythingElse(String input) {
		assertThatThrownBy(() -> RepoUrlParser.parse(input)).isInstanceOfSatisfying(ApiException.class,
				e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.INVALID_URL));
	}

	@org.junit.jupiter.api.Test
	void nameStartingWithDashIsSafeBecauseUrlAlwaysStartsWithHttps() {
		// 이름이 -로 시작해도 항상 https://github.com/ 뒤에 붙으므로 git이 옵션으로 해석하지 않는다.
		assertThat(RepoUrlParser.parse("o/-r").url()).isEqualTo("https://github.com/o/-r");
	}
}
