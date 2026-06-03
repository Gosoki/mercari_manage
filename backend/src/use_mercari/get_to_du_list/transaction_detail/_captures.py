# -*- coding: utf-8 -*-
"""shared: MITM dual-API capture wait loop"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple
from ....ssl_mitm_proxy.capture_config import read_shipping_info_response, read_transaction_messages_response
from ....web_drive.core.manager import EdgeWebDriveManager
from ....web_drive.core.mitm_session import _raise_login_required_for, login_redirect_state_for
from ....web_drive.core.paths import mercari_id_from_account_key

log = logging.getLogger(__name__)


# 等待两个 API 都被 MITM 截获的总超时（页面加载 + JS 渲染 + API 往返）
# 注意：这是「两个都迟迟不来」时的兜底上限，不是固定 sleep；只要截获齐了就立刻返回。
_WAIT_TIMEOUT_SEC = 30

# 期间每隔多少秒重新 navigate 一次（兜底：偶发未触发 API）
_RELOAD_INTERVAL_SEC = 20.0

# 已截获其中一个后，最多再等多少秒等另一个；超时即用现有结果继续。
# 某些待办本就只会触发一个接口（例如尚无发货证据时 shipping/get_info 根本不发起），
# 此时若死等两个会白白耗满总超时——一旦拿到其一就只留这点宽限给另一个。
_AFTER_FIRST_GRACE_SEC = 4.0

async def _wait_for_both_captures(
    *,
    mgr: EdgeWebDriveManager,
    auto_key: str,
    start_url: str,
    since_ms: int,
    timeout: int = _WAIT_TIMEOUT_SEC,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """同一轮询循环里等两个文件，避免互相干扰的 reload。

    每次迭代都会检查实时登录跳转监听器是否触发；命中则提前抛
    ``MercariLoginRequiredError``，不再等满 timeout。
    """
    aid_for_login = mercari_id_from_account_key(auto_key)
    deadline = time.monotonic() + timeout
    next_reload = time.monotonic() + _RELOAD_INTERVAL_SEC
    shipping: Optional[Dict[str, Any]] = None
    messages: Optional[Dict[str, Any]] = None
    first_capture_at: Optional[float] = None  # 首个接口截获到的时刻（用于宽限提前返回）
    while time.monotonic() < deadline:
        if aid_for_login is not None and login_redirect_state_for(aid_for_login):
            _raise_login_required_for(aid_for_login)
        if shipping is None:
            d = read_shipping_info_response()
            if d and int(d.get("ts") or 0) >= since_ms:
                shipping = d
        if messages is None:
            d = read_transaction_messages_response()
            if d and int(d.get("ts") or 0) >= since_ms:
                messages = d
        # 两个都截获 → 立刻进入下一步，不等满超时
        if shipping is not None and messages is not None:
            return shipping, messages
        # 只截获其一 → 记录首次命中时刻，仅再等 _AFTER_FIRST_GRACE_SEC；
        # 超过仍只有一个，说明另一个本就不会发起，用现有结果继续（避免空等总超时）
        if shipping is not None or messages is not None:
            now = time.monotonic()
            if first_capture_at is None:
                first_capture_at = now
            elif now - first_capture_at >= _AFTER_FIRST_GRACE_SEC:
                return shipping, messages
        if time.monotonic() >= next_reload:
            next_reload += _RELOAD_INTERVAL_SEC
            try:
                await mgr.reload_active_tab(auto_key, start_url)
            except Exception as exc:
                log.debug("[txdetail] reload 失败（忽略）：%s", exc)
        await asyncio.sleep(0.35)
    if aid_for_login is not None and login_redirect_state_for(aid_for_login):
        _raise_login_required_for(aid_for_login)
    return shipping, messages
