package com.codemap.api.analysis;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SourceRepoRepository extends JpaRepository<SourceRepo, Long> {

	Optional<SourceRepo> findByUrl(String url);
}
