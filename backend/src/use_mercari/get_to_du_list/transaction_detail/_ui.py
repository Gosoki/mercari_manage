# -*- coding: utf-8 -*-
"""shared: click visible button by text helper"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)


async def _click_visible_button_by_text(page: Any, text: str, *, timeout_ms: int = 8000) -> bool:
    """可視かつ有効な「text」ボタンを探してクリック（モーダル内のボタンも対象）。

    role=button → ``button:has-text`` の順で候補を集め、**非表示の複製（portal/template）を
    避けるため可視・有効なものだけ**をクリックする。出現するまで短間隔でポーリング。
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for loc in (
            page.get_by_role("button", name=text),
            page.locator(f'button:has-text("{text}")'),
        ):
            try:
                n = await loc.count()
            except Exception:
                n = 0
            for i in range(n):
                b = loc.nth(i)
                try:
                    if await b.is_visible() and await b.is_enabled():
                        await b.click()
                        return True
                except Exception:
                    continue
        await asyncio.sleep(0.3)
    return False
