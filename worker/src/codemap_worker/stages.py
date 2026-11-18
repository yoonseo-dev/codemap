"""5단계 정의. Phase 2부터 INGEST·STRUCTURE가 진짜이고 나머지는 가짜 구현이다.
가짜 단계(FAKE_STAGE_FUNCTIONS)는 Phase 3·4·5에서 하나씩 진짜 로직으로 바꾼다.

단계 함수 모양: `run(ctx, report)`.
`report(percent, detail, metrics)`는 진행률을 알리는 콜백이다. 얼마나 자주 DB·Redis에 쓸지는
호출하는 쪽(pipeline)이 정하므로 단계 함수는 마음 편히 자주 불러도 된다.
분석 실패는 `StageError`로 알린다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from codemap_worker.fake_graph import fake_history, fake_semantic
from codemap_worker.ingest import IngestConfig, IngestResult, ingest
from codemap_worker.models import STAGES, GraphEdge, GraphNode, StageError, StageName
from codemap_worker.structure.analyze import StructureResult, analyze
from codemap_worker.structure.parse import parse_file


class Report(Protocol):
    def __call__(self, percent: int, detail: str | None, metrics: dict[str, float]) -> None: ...


@dataclass
class Artifacts:
    """앞 단계가 만든 결과를 뒤 단계에 넘기는 통. 단계 함수가 채운다.
    재시도(`fromStage`)로 앞 단계를 건너뛰면 비어 있으므로, 뒤 단계는 없을 때 스스로 다시 만든다."""

    ingest: IngestResult | None = None
    structure: StructureResult | None = None


@dataclass(frozen=True)
class StageContext:
    job_id: int
    repo_url: str
    commit_sha: str
    stage_seconds: float = 1.0
    fail_stage: StageName | None = None
    sleep: Callable[[float], None] = time.sleep
    store: Any = None  # codemap_worker.store.Store (진짜 단계가 결과를 저장할 때 쓴다)
    ingest_config: IngestConfig | None = None
    artifacts: Artifacts = field(default_factory=Artifacts)


StageFn = Callable[[StageContext, Report], None]

_STEPS = 5  # 0→100%를 이 횟수로 나눠 올린다


def _fake(stage: StageName, line: Callable[[float], tuple[str, dict[str, float]]]) -> StageFn:
    """진행률이 `_STEPS`번에 걸쳐 오르는 가짜 단계. line(비율) → (detail, metrics)."""

    def run(ctx: StageContext, report: Report) -> None:
        for i in range(1, _STEPS + 1):
            ctx.sleep(ctx.stage_seconds / _STEPS)
            ratio = i / _STEPS
            if ctx.fail_stage == stage and i == 3:
                # 실패 화면·재시도 확인용. 60% 지점에서 멈춘다.
                raise StageError("FAKE_FAILURE", f"{stage.value} 단계를 일부러 실패시켰어요", True)
            detail, metrics = line(ratio)
            report(int(ratio * 100), detail, metrics)

    return run


def _n(x: float) -> int:
    return round(x)


# 아직 실제 분석이 아닌 단계의 상세 문구 끝에 붙인다. 화면에 그대로 보이므로 오해하지 않게 한다.
TEMP = " (임시 값)"


def _maybe_fail(ctx: StageContext, stage: StageName, report: Report) -> None:
    """진짜 단계에서도 CODEMAP_FAKE_FAIL_STAGE로 실패 화면을 확인할 수 있게 한다."""
    if ctx.fail_stage == stage:
        report(60, None, {})
        raise StageError("FAKE_FAILURE", f"{stage.value} 단계를 일부러 실패시켰어요", True)


# ---------- INGEST (진짜) ----------

def _ingest_result(ctx: StageContext) -> IngestResult:
    """수집 결과. 재시도로 INGEST를 건너뛰었으면 받아 둔 폴더를 재사용해 다시 만든다(없으면 다시 clone)."""
    if ctx.artifacts.ingest is None:
        if ctx.ingest_config is None:
            raise StageError("INTERNAL", "수집 설정이 없어요", True)
        ctx.artifacts.ingest = ingest(ctx.repo_url, ctx.commit_sha, ctx.ingest_config, lambda *a: None)
    return ctx.artifacts.ingest


def run_ingest(ctx: StageContext, report: Report) -> None:
    """진짜 수집: clone → 커밋 정보 → 소스 파일. 결과는 artifacts로 넘기고 커밋 시각은 DB에 쓴다."""
    if ctx.ingest_config is None:
        raise StageError("INTERNAL", "수집 설정이 없어요", True)
    result = ingest(ctx.repo_url, ctx.commit_sha, ctx.ingest_config, report)
    ctx.artifacts.ingest = result
    if ctx.store is not None:
        ctx.store.set_commit_info(ctx.job_id, result.commit.branch, result.commit.commit_date)
    _maybe_fail(ctx, StageName.INGEST, report)


# ---------- STRUCTURE (진짜) ----------

def run_structure(ctx: StageContext, report: Report) -> None:
    """진짜 구조 분석: 파싱 → 해석 → 노드·call·import 엣지를 저장한다(기존 행은 교체)."""
    ing = _ingest_result(ctx)
    files = ing.collected.files
    total = len(files)
    report(2, f"소스 파일 {total:,}개를 읽는 중이에요", {"sourceFiles": total})

    symbols = []
    unreadable = 0
    for i, f in enumerate(files, 1):
        try:
            source = (ing.root / f.path).read_bytes()
        except OSError:
            unreadable += 1
            continue
        symbols.append(parse_file(f.path, source, f.language))
        if i % 25 == 0 or i == total:
            report(2 + int(73 * i / total), f"파일 {i:,}/{total:,}개 분석", {"sourceFiles": total})

    report(80, "호출·import 관계를 해석하는 중이에요", {"sourceFiles": total})
    result = analyze(symbols)
    ctx.artifacts.structure = result

    report(90, "결과를 저장하는 중이에요", {"functions": len(result.nodes)})
    if ctx.store is not None:
        ctx.store.save_graph(ctx.job_id, result.nodes, result.edges)
    metrics = dict(result.metrics)
    if unreadable:
        metrics["unreadable"] = unreadable
    _maybe_fail(ctx, StageName.STRUCTURE, report)
    report(100, result.detail(), metrics)


# ---------- SEMANTIC·HISTORY (가짜: 실제 노드 위에 얹는다) ----------

def _graph(ctx: StageContext) -> tuple[list[GraphNode], list[GraphEdge]]:
    """가짜 단계가 얹을 실제 노드와 구조 엣지. STRUCTURE를 건너뛴 재시도면 DB에서 읽는다."""
    if ctx.artifacts.structure is not None:
        r = ctx.artifacts.structure
        return r.nodes, r.edges
    nodes, edges = ctx.store.load_graph(ctx.job_id)
    if not nodes:
        raise StageError("INTERNAL", "앞 단계(구조 지도) 결과가 없어요", True)
    return nodes, edges


def _fake_stage_over_real_nodes(
    stage: StageName,
    apply: Callable[[StageContext, list[GraphNode], list[GraphEdge]], dict[str, float]],
    running_line: Callable[[int], str],
    done_line: Callable[[dict[str, float]], str],
) -> StageFn:
    """가짜 진행률을 `_STEPS`번에 걸쳐 올리고, 끝에서 실제 노드 기반의 가짜 결과를 저장한다.
    metrics의 `fake: 1`은 Phase 3·4에서 진짜로 바뀔 임시 값이라는 표시다."""

    def run(ctx: StageContext, report: Report) -> None:
        nodes, edges = _graph(ctx)
        for i in range(1, _STEPS):
            ctx.sleep(ctx.stage_seconds / _STEPS)
            if ctx.fail_stage == stage and i == 3:
                raise StageError("FAKE_FAILURE", f"{stage.value} 단계를 일부러 실패시켰어요", True)
            report(int(100 * i / _STEPS), running_line(round(len(nodes) * i / _STEPS)), {"fake": 1})
        ctx.sleep(ctx.stage_seconds / _STEPS)
        metrics = {**apply(ctx, nodes, edges), "fake": 1}
        report(100, done_line(metrics), metrics)

    return run


def _apply_semantic(ctx: StageContext, nodes: list[GraphNode], _edges: list[GraphEdge]) -> dict[str, float]:
    positions, similar = fake_semantic(nodes, ctx.commit_sha)
    ctx.store.set_positions(ctx.job_id, positions)
    ctx.store.replace_edges(ctx.job_id, ["similar"], similar)
    return {"embedded": len(nodes), "total": len(nodes), "similarPairs": len(similar)}


def _apply_history(ctx: StageContext, nodes: list[GraphNode], edges: list[GraphEdge]) -> dict[str, float]:
    cochange = fake_history(nodes, edges, ctx.commit_sha)
    ctx.store.replace_edges(ctx.job_id, ["cochange"], cochange)
    return {"pairs": len(cochange)}


FAKE_STAGE_FUNCTIONS: dict[StageName, StageFn] = {
    StageName.INGEST: _fake(
        StageName.INGEST,
        lambda r: (
            f"커밋 {_n(2000 * r):,}개를 받고 대량 커밋 {_n(37 * r)}개는 뺐어요",
            {"commits": _n(2000 * r), "bulkExcluded": _n(37 * r)},
        ),
    ),
    StageName.STRUCTURE: _fake(
        StageName.STRUCTURE,
        lambda r: (
            f"함수 {_n(2418 * r):,}개, 호출 관계 {_n(1284 * r):,}개, 해석 성공률 87%",
            {"functions": _n(2418 * r), "edges": _n(1284 * r), "resolvedRate": 0.87},
        ),
    ),
    StageName.SEMANTIC: _fake(
        StageName.SEMANTIC,
        lambda r: (
            f"함수 2,418개 중 {_n(2418 * r):,}개 임베딩",
            {"embedded": _n(2418 * r), "total": 2418},
        ),
    ),
    StageName.HISTORY: _fake(
        StageName.HISTORY,
        lambda r: (
            f"함께 수정된 함수 짝 {_n(312 * r)}개를 찾았어요",
            {"pairs": _n(312 * r)},
        ),
    ),
    StageName.DIVERGENCE: _fake(
        StageName.DIVERGENCE,
        lambda r: (
            f"어긋남 후보 {_n(41 * r)}개를 골랐어요",
            {"candidates": _n(41 * r)},
        ),
    ),
}

# 지금 쓰는 단계 함수. SEMANTIC·HISTORY는 실제 노드 위에 가짜 결과를 얹고, DIVERGENCE는 아직 완전히 가짜다.
STAGE_FUNCTIONS: dict[StageName, StageFn] = {
    **FAKE_STAGE_FUNCTIONS,
    StageName.INGEST: run_ingest,
    StageName.STRUCTURE: run_structure,
    StageName.SEMANTIC: _fake_stage_over_real_nodes(
        StageName.SEMANTIC,
        _apply_semantic,
        lambda done: f"함수 {done:,}개 임베딩 중{TEMP}",
        lambda m: f"함수 {m['total']:,.0f}개 중 {m['embedded']:,.0f}개 임베딩{TEMP}",
    ),
    StageName.HISTORY: _fake_stage_over_real_nodes(
        StageName.HISTORY,
        _apply_history,
        lambda done: f"함께 수정된 함수 짝을 찾는 중이에요{TEMP}",
        lambda m: f"함께 수정된 함수 짝 {m['pairs']:,.0f}개를 찾았어요{TEMP}",
    ),
    # 어긋남 탐지는 Phase 5 전까지 완전히 가짜다. 숫자(41)도 항상 같다.
    StageName.DIVERGENCE: _fake(
        StageName.DIVERGENCE,
        lambda r: (
            f"어긋남 후보 {_n(41 * r)}개를 골랐어요{TEMP}",
            {"candidates": _n(41 * r), "fake": 1},
        ),
    ),
}

assert set(STAGE_FUNCTIONS) == set(STAGES)
