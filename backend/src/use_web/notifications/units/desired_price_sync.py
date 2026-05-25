# -*- coding: utf-8 -*-
"""降价请求(値下げ依頼)详情同步入口(HTTP 层)。"""

from typing import Any, Dict

from fastapi import HTTPException

from ....use_mercari.get_notifications.desired_price_sync import (
    _resolve_account_id,
    sync_desired_price_from_mercari,
)
from .desired_price_models import DesiredPriceSyncRequest


async def sync_desired_price(req: DesiredPriceSyncRequest) -> Dict[str, Any]:
    """打开 desired_price 页捕获响应并入库。不走队列, 复用主 profile 浏览器。"""
    iid = (req.item_id or "").strip()
    if not iid:
        raise HTTPException(status_code=400, detail="item_id 不能为空")
    try:
        aid = _resolve_account_id(req.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        stats = await sync_desired_price_from_mercari(
            item_id=iid,
            account_id=aid,
            notification_id=req.notification_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return stats
