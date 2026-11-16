package com.codemap.api.analysis;

import com.codemap.api.common.PublicId;

/** 응답의 {@code repository: { id, owner, name, url }} */
public record RepositoryResponse(String id, String owner, String name, String url) {

	public static RepositoryResponse of(SourceRepo repo) {
		return new RepositoryResponse(PublicId.repo(repo.getId()), repo.getOwner(), repo.getName(), repo.getUrl());
	}
}
