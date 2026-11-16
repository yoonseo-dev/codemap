package com.codemap.api.analysis;

/** 원격 저장소 HEAD의 커밋 SHA와 기본 브랜치. branch는 알 수 없으면 null */
public record RemoteHead(String sha, String branch) {
}
