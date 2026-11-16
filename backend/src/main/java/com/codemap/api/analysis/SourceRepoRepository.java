package com.codemap.api.analysis;

import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SourceRepoRepository extends JpaRepository<SourceRepo, Long> {

	Optional<SourceRepo> findByUrl(String url);

	/** 같은 저장소의 분석 시작을 한 줄로 세운다(행 잠금). 확인과 작업 생성 사이에 다른 요청이 끼어들지 못하게 한다. */
	@Lock(LockModeType.PESSIMISTIC_WRITE)
	@Query("select r from SourceRepo r where r.id = :id")
	Optional<SourceRepo> findByIdForUpdate(@Param("id") Long id);
}
