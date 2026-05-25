# -*- coding: utf-8 -*-
"""降价请求(値下げ依頼)详情查询(DB 层)。"""

import json
from typing import Any, Dict, List, Optional

from ....db_manage.database import DatabaseManager

_DETAIL_COLS = (
    "id",
    "account_id",
    "item_id",
    "notification_id",
    "offer_name",
    "offer_type",
    "offered_price",
    "buyer_id",
    "buyer_username",
    "buyer_photo",
    "buyer_score",
    "buyer_reviews_count",
    "item_name",
    "item_photo",
    "item_price",
    "item_status",
    "state",
    "create_time",
    "expire_time",
    "raw_json",
    "raw_item_json",
    "synced_at",
)


def _safe_json_loads(s: Any) -> Any:
    if s is None or s == "":
        return None
    if not isinstance(s, str):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _row_to_dict(row: tuple) -> Dict[str, Any]:
    d = dict(zip(_DETAIL_COLS, row))
    raw = _safe_json_loads(d.get("raw_json"))
    d["raw"] = raw
    # 整理 offers 列表给前端展示
    offers: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        for item in raw.get("aggregatedDesiredPrices") or []:
            if not isinstance(item, dict):
                continue
            buyer = item.get("buyer") if isinstance(item.get("buyer"), dict) else {}
            offers.append(
                {
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "price": item.get("price"),
                    "create_time": item.get("createTime"),
                    "expire_time": item.get("expireTime"),
                    "buyer_id": buyer.get("userId"),
                    "buyer_username": buyer.get("username"),
                    "buyer_photo": buyer.get("profileImageUri"),
                    "buyer_score": buyer.get("score"),
                    "buyer_reviews_count": buyer.get("reviewsCount"),
                }
            )
    d["offers"] = offers
    return d


def get_desired_price_offer(
    item_id: str, account_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """按 item_id 取出降价请求详情; account_id 可选用于多账号隔离。"""
    iid = str(item_id or "").strip()
    if not iid:
        return None
    db = DatabaseManager()
    sel_cols = ", ".join(f"[{c}]" for c in _DETAIL_COLS)
    if account_id is not None:
        rows = db.execute_query(
            f"SELECT {sel_cols} FROM [desired_price_offers] "
            "WHERE [item_id] = ? AND [account_id] = ? LIMIT 1",
            (iid, int(account_id)),
        )
    else:
        rows = db.execute_query(
            f"SELECT {sel_cols} FROM [desired_price_offers] "
            "WHERE [item_id] = ? ORDER BY [id] DESC LIMIT 1",
            (iid,),
        )
    if not rows:
        return None
    return _row_to_dict(rows[0])
