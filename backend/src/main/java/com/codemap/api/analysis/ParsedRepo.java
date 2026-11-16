package com.codemap.api.analysis;

/** 사용자가 입력한 저장소 주소를 해석한 결과. url은 항상 {@code https://github.com/owner/name} 형태다. */
public record ParsedRepo(String owner, String name, String url) {
}
