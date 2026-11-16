package com.codemap.api.analysis;

/** 원격 저장소를 clone하지 않고 HEAD만 확인한다. 테스트가 인터넷에 의존하지 않도록 인터페이스로 둔다. */
public interface RemoteGit {

	/**
	 * @throws com.codemap.api.common.ApiException REPO_NOT_FOUND: 저장소가 없거나 비공개이거나 시간이 초과된 경우
	 */
	RemoteHead resolveHead(String url);
}
