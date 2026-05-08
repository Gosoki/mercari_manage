# -*- coding: utf-8 -*-
"""
订单「货物比例 / 比例价格」权重：与 routes.orders list_order_outbound_lines 中
bundle_title 分摊逻辑一致，供包材成本按归属拆分等复用。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .db_manage.database import DatabaseManager
from .db_manage.models.order_outbound_line import OrderOutboundLineModel

_db = DatabaseManager()


def owner_weights_from_order_goods_ratio(order_no: str) -> List[Dict[str, Any]]:
    """
    若订单存在可计算的 bundle_title 比例（与订单二级表「货物比例」同源），
    返回 [{"owner": 展示名同商品归属, "weight": 整数权重}, ...]；
    weight 为该归属下各组合行的 ratio_price 之和（与订单金额分摊一致）。

    无法计算时返回 []，调用方应回退其它权重口径。
    """
    ono = (order_no or "").strip()
    if not ono:
        return []

    items = OrderOutboundLineModel.list_enriched_for_order(ono)
    order_rows = _db.execute_query(
        "SELECT COALESCE([amount], 0) FROM [orders] WHERE [order_no] = ? LIMIT 1",
        (ono,),
    )
    order_amount = int(order_rows[0][0] or 0) if order_rows else 0

    bundle_lines = [
        it for it in items if str(it.get("line_kind") or "").strip() == "bundle_title"
    ]
    if not bundle_lines or order_amount <= 0:
        return []

    def _normalize_match_text(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "").strip()).casefold()

    titles: List[str] = [str(it.get("management_id") or "").strip() for it in bundle_lines]
    titles = [t for t in titles if t]
    title_set = list(dict.fromkeys(titles))

    on_sale_rows = _db.execute_query(
        """
        SELECT
            o.[item_id],
            TRIM(IFNULL(o.[name], '')) AS [name],
            COALESCE(o.[price], 0) AS [price],
            o.[updated],
            o.[created],
            o.[id]
        FROM [on_sale_items] o
        WHERE COALESCE(o.[is_delete], 0) = 0
          AND TRIM(IFNULL(o.[item_id], '')) != ''
          AND TRIM(IFNULL(o.[name], '')) != ''
        """
    )
    on_sale_records = []
    for item_id_raw, name_raw, price_raw, updated_raw, created_raw, oid_raw in on_sale_rows:
        name_str = str(name_raw or "").strip()
        item_id_str = str(item_id_raw or "").strip()
        if not name_str or not item_id_str:
            continue
        name_norm = _normalize_match_text(name_str)
        try:
            updated_i = int(updated_raw) if updated_raw is not None else 0
        except (TypeError, ValueError):
            updated_i = 0
        try:
            created_i = int(created_raw) if created_raw is not None else 0
        except (TypeError, ValueError):
            created_i = 0
        try:
            oid_i = int(oid_raw) if oid_raw is not None else 0
        except (TypeError, ValueError):
            oid_i = 0
        try:
            price_i = int(price_raw or 0)
        except (TypeError, ValueError):
            price_i = 0

        on_sale_records.append(
            {
                "item_id": item_id_str,
                "name_norm": name_norm,
                "price": price_i,
                "updated": updated_i,
                "created": created_i,
                "id": oid_i,
            }
        )

    latest_price_by_title: dict = {}
    for title in title_set:
        target_norm = _normalize_match_text(title)
        exact_candidates = []
        fuzzy_candidates = []
        for rec in on_sale_records:
            nn = rec.get("name_norm") or ""
            if not nn:
                continue
            if nn == target_norm:
                exact_candidates.append(rec)
            elif target_norm and (target_norm in nn or nn in target_norm):
                fuzzy_candidates.append(rec)
        candidates = exact_candidates if exact_candidates else fuzzy_candidates
        if not candidates:
            latest_price_by_title[title] = None
            continue
        best = max(
            candidates,
            key=lambda c: (int(c.get("updated") or 0), int(c.get("created") or 0), int(c.get("id") or 0)),
        )
        latest_price_by_title[title] = int(best.get("price") or 0)

    weights: List[int] = []
    for it in bundle_lines:
        qty = max(1, int(it.get("quantity") or 1))
        title = str(it.get("management_id") or "").strip()
        op = latest_price_by_title.get(title)
        op_int = int(op) if op is not None else 0
        w = max(0, op_int) * qty
        weights.append(w)

    sum_w = sum(weights)
    if sum_w <= 0:
        return []

    floors: List[int] = []
    fracs: List[float] = []
    for w in weights:
        raw_total = order_amount * (float(w) / float(sum_w))
        f = int(raw_total)
        floors.append(f)
        fracs.append(raw_total - f)

    remain = order_amount - sum(floors)
    alloc_totals = floors[:]
    if remain > 0:
        idxs = sorted(range(len(fracs)), key=lambda i: fracs[i], reverse=True)
        for i in idxs[:remain]:
            alloc_totals[i] += 1

    grouped: Dict[str, int] = {}
    for i, it in enumerate(bundle_lines):
        rp = int(alloc_totals[i])
        owner = str(it.get("product_owner_name") or "").strip()
        if not owner:
            continue
        grouped[owner] = int(grouped.get(owner, 0)) + rp

    return [
        {"owner": k, "weight": int(v)}
        for k, v in grouped.items()
        if int(v) > 0
    ]
