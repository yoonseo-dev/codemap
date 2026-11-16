package com.codemap.api.analysis;

import com.codemap.api.common.ApiException;
import com.codemap.api.common.ErrorCode;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * GitHub 저장소 주소를 {@code owner}, {@code name}, 정규화된 URL로 바꾼다.
 * 받는 형식: {@code owner/repo}, {@code github.com/owner/repo}, {@code https://github.com/owner/repo},
 * 끝에 {@code .git}이나 {@code /}가 붙은 것. 그 외는 INVALID_URL.
 *
 * <p>검증된 owner·name만 URL로 조립하므로, 이 결과는 {@code git} 인자로 넘겨도 옵션 주입이 일어나지 않는다.
 */
public final class RepoUrlParser {

	private static final Pattern SCHEME = Pattern.compile("^https?://", Pattern.CASE_INSENSITIVE);
	private static final String HOST = "github.com";
	private static final Pattern OWNER = Pattern.compile("[A-Za-z0-9][A-Za-z0-9-]{0,38}");
	private static final Pattern NAME = Pattern.compile("[A-Za-z0-9._-]{1,100}");

	private RepoUrlParser() {
	}

	public static ParsedRepo parse(String input) {
		if (input == null) {
			throw invalid();
		}
		String rest = input.trim();

		boolean hasScheme = false;
		var scheme = SCHEME.matcher(rest);
		if (scheme.find()) {
			hasScheme = true;
			rest = rest.substring(scheme.end());
		}
		if (rest.regionMatches(true, 0, "www.", 0, 4)) {
			rest = rest.substring(4);
		}
		boolean hasHost = rest.regionMatches(true, 0, HOST + "/", 0, HOST.length() + 1);
		if (hasHost) {
			rest = rest.substring(HOST.length() + 1);
		}
		else if (hasScheme) {
			throw invalid(); // https://gitlab.com/... 처럼 호스트가 GitHub가 아님
		}

		while (rest.endsWith("/")) {
			rest = rest.substring(0, rest.length() - 1);
		}
		if (rest.toLowerCase(Locale.ROOT).endsWith(".git")) {
			rest = rest.substring(0, rest.length() - 4);
		}

		String[] parts = rest.split("/", -1);
		if (parts.length != 2) {
			throw invalid();
		}
		String owner = parts[0];
		String name = parts[1];
		if (!OWNER.matcher(owner).matches() || !NAME.matcher(name).matches() || name.equals(".")
				|| name.equals("..")) {
			throw invalid();
		}
		return new ParsedRepo(owner, name, "https://" + HOST + "/" + owner + "/" + name);
	}

	private static ApiException invalid() {
		return new ApiException(ErrorCode.INVALID_URL);
	}
}
