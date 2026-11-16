package com.codemap.api.analysis;

import com.codemap.api.job.StageName;

/**
 * 큐로 보내는 작업 메시지. 워커의 {@code JobMessage}(worker/messages.py)와 필드가 같아야 한다.
 *
 * @param jobId     DB의 bigint ID. API의 {@code j_12} 형식이 아니다.
 * @param fromStage 재시도할 때 시작 단계. 처음 실행이면 null
 */
public record JobMessage(long jobId, String repoUrl, String commitSha, StageName fromStage) {
}
