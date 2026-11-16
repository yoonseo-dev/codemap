"""Phase 1 가짜 그래프. 시드가 고정이라 실행할 때마다 같은 결과가 나온다.

모양은 프론트 mock(`frontend/src/api/mock/fixtures.ts`)과 비슷하다: 모듈 6개, 함수 약 200개,
엣지 4종류(call·import·similar·cochange). Phase 2부터 실제 분석 결과로 바뀐다.
"""

import random
from datetime import UTC, datetime, timedelta

from codemap_worker.models import GraphEdge, GraphNode

SEED = 20261116

# (모듈 id, 의미 지도 중심, 파일, 이름을 정해 둔 함수들 — 첫 번째가 폴더 대표 함수)
_MODULES: list[tuple[str, tuple[float, float, float], list[str], list[str]]] = [
    ("billing/", (-2.5, -0.4, 0.6), ["invoice.py", "tax.py", "refund.py", "report.py"], [
        "billing/invoice.py::InvoiceService.create", "billing/invoice.py::calc_total",
        "billing/tax.py::rate_for", "billing/report.py::to_rows",
        "billing/invoice.py::send_receipt", "billing/refund.py::refund_amount"]),
    ("orders/", (2.4, 0.5, -0.4), ["service.py", "cart.py", "controller.py"], [
        "orders/controller.py::OrderController.place", "orders/cart.py::sum_items",
        "orders/service.py::place_order", "orders/service.py::send_order_mail",
        "orders/service.py::OrderService.reserve_stock"]),
    ("auth/", (-0.4, -2.1, -1.7), ["session.py", "signup.py", "profile.py"], [
        "auth/session.py::SessionStore.get", "auth/session.py::refresh",
        "auth/signup.py::validate_email", "auth/profile.py::normalize_phone",
        "auth/session.py::require_login"]),
    ("api/", (0.1, 0.2, 1.3), ["router.py", "validators.py", "routes.py", "export.py"], [
        "api/router.py::dispatch", "api/validators.py::check_email",
        "api/routes.py::export_csv", "api/export.py::sum_rows"]),
    ("notify/", (-2.1, 1.8, -0.6), ["mailer.py", "sms.py", "sender.py"], [
        "notify/mailer.py::Mailer.deliver", "notify/mailer.py::render_template",
        "notify/sms.py::format_phone", "notify/mailer.py::send",
        "notify/sms.py::send_sms", "notify/mailer.py::send_bulk"]),
    ("catalog/", (2.5, -2.0, 0.8), ["price.py", "product.py"], [
        "catalog/price.py::PriceRule.apply", "catalog/price.py::apply_discount",
        "catalog/price.py::line_total"]),
]

_FILLER = ["load", "save", "parse", "build", "to_dict", "from_row", "validate", "normalize",
           "format", "fetch", "update", "remove", "merge", "split", "lookup", "resolve"]

# 눈에 띄게 만든 어긋남 후보: 하는 일은 같은데 서로 다른 모듈에 있는 함수들
_DUPLICATES = [
    ("billing/invoice.py::calc_total", "orders/cart.py::sum_items", 0.94),
    ("orders/cart.py::sum_items", "api/export.py::sum_rows", 0.91),
    ("billing/invoice.py::send_receipt", "orders/service.py::send_order_mail", 0.89),
    ("auth/signup.py::validate_email", "api/validators.py::check_email", 0.93),
    ("auth/profile.py::normalize_phone", "notify/sms.py::format_phone", 0.88),
]
# 호출 관계는 없는데 함께 수정되는 함수들 (숨은 결합)
_HIDDEN_COUPLING = [
    ("billing/tax.py::rate_for", "catalog/price.py::apply_discount", 0.82),
    ("orders/service.py::OrderService.reserve_stock", "notify/mailer.py::send_bulk", 0.71),
    ("auth/session.py::refresh", "api/router.py::dispatch", 0.66),
]

_BASE_DATE = datetime(2025, 11, 1, tzinfo=UTC)


def _name(node_id: str) -> str:
    return node_id.split("::")[1]


def make_fake_graph(seed: int = SEED) -> tuple[list[GraphNode], list[GraphEdge]]:
    rnd = random.Random(seed)

    raw: list[tuple[str, str, tuple[float, float, float], int]] = []  # (id, module, center, idx)
    for module_id, center, files, named in _MODULES:
        ids = list(named)
        for i in range(rnd.randint(26, 34)):
            fn = _FILLER[(i * 7 + len(module_id)) % len(_FILLER)]
            ids.append(f"{module_id}{files[i % len(files)]}::{fn}_{i}")
        raw.extend((node_id, module_id, center, idx) for idx, node_id in enumerate(ids))

    by_module: dict[str, list[str]] = {}
    for node_id, module_id, _, _ in raw:
        by_module.setdefault(module_id, []).append(node_id)
    module_ids = list(by_module)

    def structure_edges() -> list[GraphEdge]:
        seen: set[tuple[str, str, str]] = set()
        out: list[GraphEdge] = []

        def add(source: str, target: str, kind: str, weight: float) -> None:
            if source == target or (source, target, kind) in seen:
                return
            seen.add((source, target, kind))
            out.append(GraphEdge(source, target, kind, weight))

        for node_id, module_id, _, idx in raw:
            for _ in range(rnd.randint(1, 3)):
                # 대부분은 같은 모듈 안에서 부르고, 가끔 다른 모듈을 부른다
                pool = by_module[module_id] if rnd.random() < 0.8 else by_module[rnd.choice(module_ids)]
                # 대표 함수(앞쪽)가 더 많이 불리도록 앞쪽에 가중치
                target = pool[min(int(rnd.random() ** 2 * len(pool)), len(pool) - 1)]
                add(node_id, target, "call", float(rnd.randint(1, 5)))
        # import: 모듈 대표 함수끼리 서로 가져온다
        for a in module_ids:
            for b in rnd.sample([m for m in module_ids if m != a], 2):
                add(by_module[a][0], by_module[b][0], "import", 1.0)
        return out

    edges = structure_edges()
    call_pairs = {(e.source, e.target) for e in edges} | {(e.target, e.source) for e in edges}

    # similar: 모듈 안의 비슷한 함수 + 모듈을 가로지르는 중복 구현
    for node_id, module_id, _, _ in raw:
        if rnd.random() < 0.12:
            other = rnd.choice(by_module[module_id])
            if other != node_id:
                edges.append(GraphEdge(node_id, other, "similar", round(rnd.uniform(0.70, 0.86), 2)))
    edges.extend(GraphEdge(a, b, "similar", w) for a, b, w in _DUPLICATES)

    # cochange: 같이 부르는 함수는 같이 수정되기 쉽다 + 호출 관계 없는 숨은 결합
    for e in [e for e in edges if e.kind == "call"]:
        if rnd.random() < 0.15:
            since = _BASE_DATE + timedelta(days=rnd.randint(0, 330))
            edges.append(GraphEdge(e.source, e.target, "cochange", round(rnd.uniform(0.5, 0.9), 2), since))
    for a, b, w in _HIDDEN_COUPLING:
        assert (a, b) not in call_pairs, "숨은 결합 견본은 호출 관계가 없어야 한다"
        since = _BASE_DATE + timedelta(days=rnd.randint(0, 120))
        edges.append(GraphEdge(a, b, "cochange", w, since))

    degree: dict[str, int] = {node_id: 0 for node_id, *_ in raw}
    for e in edges:
        if e.kind in ("call", "import"):
            degree[e.source] += 1
            degree[e.target] += 1

    def gauss(spread: float) -> float:
        return rnd.gauss(0, spread)

    nodes: list[GraphNode] = []
    for node_id, module_id, center, idx in raw:
        start = rnd.randint(10, 210)
        spread = 0.15 if idx == 0 else 0.7
        name = _name(node_id)
        nodes.append(
            GraphNode(
                id=node_id,
                name=name,
                path=node_id.split("::")[0],
                module_id=module_id,
                kind="method" if "." in name else "function",
                start_line=start,
                end_line=start + rnd.randint(6, 45),
                degree=degree[node_id],
                sem=(
                    round(center[0] + gauss(spread), 3),
                    round(center[1] + gauss(spread), 3),
                    round(center[2] + gauss(spread), 3),
                ),
            )
        )
    return nodes, edges
