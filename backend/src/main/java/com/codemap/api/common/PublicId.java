package com.codemap.api.common;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * DB의 bigint ID와 API의 문자열 ID({@code j_12}, {@code r_3}) 사이를 바꾼다.
 * 워커가 이벤트에 넣는 jobId도 같은 형식이어야 한다(worker/events.py).
 */
public final class PublicId {

	private static final Pattern JOB = Pattern.compile("j_([0-9]{1,18})");
	private static final Pattern REPO = Pattern.compile("r_([0-9]{1,18})");

	private PublicId() {
	}

	public static String job(long id) {
		return "j_" + id;
	}

	public static String repo(long id) {
		return "r_" + id;
	}

	/** 형식이 틀리면 JOB_NOT_FOUND. 400이 아닌 이유: 화면 입장에서는 "없는 작업"과 같다. */
	public static long parseJob(String publicId) {
		return parse(JOB, publicId, ErrorCode.JOB_NOT_FOUND);
	}

	public static long parseRepo(String publicId) {
		return parse(REPO, publicId, ErrorCode.REPO_NOT_FOUND);
	}

	private static long parse(Pattern pattern, String publicId, ErrorCode onInvalid) {
		Matcher m = publicId == null ? null : pattern.matcher(publicId);
		if (m == null || !m.matches()) {
			throw new ApiException(onInvalid);
		}
		return Long.parseLong(m.group(1));
	}
}
