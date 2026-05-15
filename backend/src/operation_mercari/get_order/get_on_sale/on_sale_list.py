# -*- coding: utf-8 -*-
"""
Mercari 在售商品列表：通过账号对应 WebDriver 打开
``https://jp.mercari.com/mypage/listings``（经 SSL 中间人代理），
由 mitmproxy 截获 ``GET https://api.mercari.jp/items/get_items``（status 含 on_sale/stop）
的响应体，不再直接 HTTP 调用 API。

MITM 无头浏览器使用独立 profile：``meilu_{account_id}__auto``（与账号页有头 ``meilu_{account_id}`` 分离）。
截获完成后会在 ``finally`` 中关闭该账号浏览器会话。
环境变量 ``WEB_DRIVE_MERCARI_HEADLESS`` 或 ``WEB_DRIVE_ON_SALE_SYNC_HEADLESS``：默认 ``1`` 为无头。
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from ....ssl_mitm_proxy.capture_config import (
    clear_on_sale_list_response_file,
    read_on_sale_list_response,
)
from ....ssl_mitm_proxy.runner import start_mitm_proxy
from ....web_drive.manager import EdgeWebDriveManager
from ....web_drive.mitm_session import mitm_automation_browser, wait_mitm_capture

_API_BASE = "https://api.mercari.jp/items/get_items"
LISTINGS_PAGE_URL = "https://jp.mercari.com/mypage/listings"
LISTINGS_URL_FRAGMENT = "mypage/listings"
LISTINGS_REDIRECT_TIMEOUT_MS = 60_000


def build_on_sale_list_url(seller_id: int) -> str:
    """
    与页面触发的查询参数一致（seller_id 可变，其余固定），便于对照抓包。
    """
    params = {
        "order_by": "desc",
        "seller_id": str(int(seller_id)),
        "sort_type": "updated",
        "status": "on_sale,stop",
        "with_action_hints": "false",
        "with_auction": "true",
        "with_enhanced_hints": "true",
        "with_impression_boost": "true",
        "with_total_item_count": "false",
    }
    return f"{_API_BASE}?{urlencode(params)}"


def _on_sale_sync_headless() -> bool:
    v = (
        os.environ.get("WEB_DRIVE_MERCARI_HEADLESS")
        or os.environ.get("WEB_DRIVE_ON_SALE_SYNC_HEADLESS")
        or "1"
    ).strip().lower()
    return v in ("1", "true", "yes", "on")


def _parse_on_sale_list_capture(seller_key: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    wrapped = read_on_sale_list_response(seller_key) or {}
    body = wrapped.get("body")
    if not isinstance(body, dict):
        raise RuntimeError(f"截获数据格式异常: {wrapped!r}")
    if body.get("result") != "OK":
        raise RuntimeError(f"API 返回异常: {body}")
    items: List[Dict[str, Any]] = body.get("data") or []
    meta: Dict[str, Any] = body.get("meta") or {}
    return items, meta


async def _fetch_on_sale_via_browser_impl(
    account_id: int,
    seller_id: int,
    *,
    timeout: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    seller_key = str(int(seller_id))
    clear_on_sale_list_response_file(seller_key)
    since_ms = int(time.time() * 1000)
    headless = _on_sale_sync_headless()

    async with mitm_automation_browser(
        account_id,
        start_url=LISTINGS_PAGE_URL,
        headless=headless,
    ) as (mgr, auto_key):
        await wait_mitm_capture(
            mgr=mgr,
            auto_key=auto_key,
            start_url=LISTINGS_PAGE_URL,
            read_response=lambda: read_on_sale_list_response(seller_key),
            since_ms=since_ms,
            wait_seconds=timeout,
            error_detail=(
                f"在售列表 items/get_items（on_sale,stop），seller_id={seller_key}"
            ),
        )

    return _parse_on_sale_list_capture(seller_key)


async def fetch_on_sale_list_items(
    seller_id: int,
    account_id: Optional[int] = None,
    timeout: int = 90,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    使用对应账号的 Edge 会话（经 MITM）打开出品一覧页，从代理截获的
    ``items/get_items`` 响应中解析 ``data`` 与 ``meta``。

    :raises RuntimeError: 未配置 account_id、MITM/浏览器失败或响应 result!=OK
    """
    if account_id is None:
        raise RuntimeError(
            "在售列表改为网页+MITM 截获后，必须提供 account_id（同步入口会传入煤炉账号主键）"
        )
    return await _fetch_on_sale_via_browser_impl(
        int(account_id),
        int(seller_id),
        timeout=int(timeout),
    )


async def sync_on_sale_from_listings_browser_page(
    manager: EdgeWebDriveManager,
    account_key: str,
    seller_id: int,
    page: Any,
    *,
    capture_since_ms: int,
    timeout: int = 90,
) -> Dict[str, Any]:
    """
    删除商品后浏览器跳转到出品一覧页时：复用当前有头会话 + MITM，
    截获 items/get_items（on_sale,stop）并执行与「从煤炉同步」相同的本地更新。
    """
    r = start_mitm_proxy()
    if r.get("error"):
        raise RuntimeError(f"MITM 代理不可用: {r['error']}")

    seller_key = str(int(seller_id))

    try:
        await page.wait_for_url(
            lambda u: LISTINGS_URL_FRAGMENT in (u or "").lower(),
            timeout=LISTINGS_REDIRECT_TIMEOUT_MS,
        )
    except Exception as exc:
        raise RuntimeError(
            f"删除后未跳转到出品一覧页（{LISTINGS_PAGE_URL}）: {exc}"
        ) from exc

    await wait_mitm_capture(
        mgr=manager,
        auto_key=account_key,
        start_url=LISTINGS_PAGE_URL,
        read_response=lambda: read_on_sale_list_response(seller_key),
        since_ms=capture_since_ms,
        wait_seconds=timeout,
        error_detail=(
            f"在售列表 items/get_items（on_sale,stop），seller_id={seller_key}"
        ),
    )

    from ...on_sale_items_sync import apply_on_sale_list_sync

    items, meta = _parse_on_sale_list_capture(seller_key)
    stats = apply_on_sale_list_sync(seller_key, items, meta)
    stats["sync_source"] = "listings_page_after_delete"
    return stats
