# -*- coding: utf-8 -*-
"""通用煤炉同步进度（内存）：供前端轮询展示「从煤炉同步」当前步骤。

与 web_drive/listing/units/listing_progress.py 同模式：按 job_id 写入步骤标签，
前端通过对应 GET /…/sync-progress/{job_id} 端点拉取展示。

供多个同步入口共享（在售商品、待办、通知）；同一进程内 job_id 唯一即可。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

_store: Dict[str, Dict[str, Any]] = {}


def set_sync_progress(
    job_id: str, step: str, label_zh: str, page_zh: Optional[str] = None
) -> None:
    """写入当前步骤。``page_zh``（如「待办事项」）表示当前同步的业务页面：
    显式传入则更新；传 ``None`` 则沿用上一次的值，使其在该页面的多个子步骤间保持不变。
    """
    if not job_id:
        return
    prev = _store.get(job_id) or {}
    _store[job_id] = {
        "step": step,
        "label_zh": label_zh,
        "page_zh": page_zh if page_zh is not None else prev.get("page_zh"),
        "ts": time.time(),
    }


def set_sync_progress_page(job_id: str, page_zh: str) -> None:
    """切换当前业务页面（用于一次性同步多个页面时标注「正在同步哪个页面」）。

    同时把子步骤文案重置为占位，避免短暂显示上一个页面的末步文案。
    """
    if not job_id:
        return
    _store[job_id] = {
        "step": "switch_page",
        "label_zh": "准备同步…",
        "page_zh": page_zh,
        "ts": time.time(),
    }


def get_sync_progress(job_id: str) -> Optional[Dict[str, Any]]:
    if not job_id:
        return None
    row = _store.get(job_id)
    if not row:
        return None
    out = dict(row)
    # 有页面标注时，把页面名拼到 label_zh 前面，前端无需改动即可显示「正在同步哪个页面」。
    page = out.get("page_zh")
    if page:
        lbl = out.get("label_zh") or ""
        out["label_zh"] = f"【{page}】{lbl}" if lbl else f"【{page}】"
    return out


def clear_sync_progress(job_id: str) -> None:
    if job_id:
        _store.pop(job_id, None)


def make_sync_reporter(job_id: Optional[str]) -> Callable[[str, str], None]:
    """生成 (step, label_zh) → 写入内存的回调；job_id 为空时返回 no-op。"""
    jid = (job_id or "").strip() or None

    def report(step: str, label_zh: str) -> None:
        if jid:
            set_sync_progress(jid, step, label_zh)

    return report
