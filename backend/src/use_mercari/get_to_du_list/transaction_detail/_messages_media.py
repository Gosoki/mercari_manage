# -*- coding: utf-8 -*-
"""交易消息图片：抓取时下载到本地 /imges 持久化缓存。

煤炉消息里的图片是 storage.googleapis.com 的签名 URL（X-Goog-Expires≈1 小时即失效），
不能直接交给前端长期引用，也不能走 mercari_image 代理（仅白名单煤炉 CDN + 按需重拉会过期）。
因此在抓取交易详情时立刻把每条消息的图片下载下来存进 backend/imges，前端只显示本地图。

幂等：以消息 id 复用上次已下载的本地图，避免「刷新抓取」重复下载/堆积；不再被引用的
旧消息图会被清理。
"""
from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ....db_manage.database import DatabaseManager
from ....use_web.image_storage import delete_image_file, get_image_root, save_image_bytes

log = logging.getLogger(__name__)

_MAX_BYTES = 20 * 1024 * 1024  # 20MB
_FETCH_TIMEOUT = 15.0  # seconds

_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
}


def _ext_from_url_or_type(url: str, content_type: Optional[str]) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[ct]
    path = urllib.parse.urlsplit(url).path.lower()
    for suf in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
        if path.endswith("." + suf):
            return "jpg" if suf == "jpeg" else suf
    return "jpg"


def _download(url: str) -> Tuple[bytes, Optional[str]]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
            "Referer": "https://jp.mercari.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        ct = resp.headers.get("Content-Type")
        data = resp.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("消息图片体积过大")
        return data, ct


def _imges_abs(path: str) -> Optional[str]:
    """把 /imges/xxx 形式的可访问路径转成磁盘绝对路径；非该前缀返回 None。"""
    if not isinstance(path, str) or not path.startswith("/imges/"):
        return None
    name = path.split("/imges/", 1)[1].strip("/")
    if not name:
        return None
    return os.path.join(get_image_root(), name)


def _load_old_messages(todo_id: int) -> List[Dict[str, Any]]:
    """读取上次缓存的 detail_json.messages（用于复用已下载的本地图）。"""
    try:
        rows = DatabaseManager().execute_query(
            "SELECT [detail_json] FROM [todo_items] WHERE [id]=?", (int(todo_id),)
        )
    except Exception:
        return []
    if not rows or not rows[0] or not rows[0][0]:
        return []
    try:
        import json

        d = json.loads(rows[0][0])
    except Exception:
        return []
    if isinstance(d, dict) and isinstance(d.get("messages"), list):
        return [m for m in d["messages"] if isinstance(m, dict)]
    return []


def _old_local_by_id(old_messages: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """消息 id → 上次已落地的本地 /imges 路径列表（文件须仍存在）。"""
    out: Dict[str, List[str]] = {}
    for m in old_messages:
        mid = str(m.get("id") or "").strip()
        if not mid:
            continue
        locals_: List[str] = []
        for p in m.get("images") or []:
            ap = _imges_abs(p) if isinstance(p, str) else None
            if ap and os.path.exists(ap):
                locals_.append(p)
        if locals_:
            out[mid] = locals_
    return out


async def cache_message_images(todo_id: int, messages: List[Dict[str, Any]]) -> None:
    """把每条消息的图片（远程签名 URL）下载到本地，并把 message["images"] 原地替换为
    本地 /imges 路径。失败的单张图被丢弃（避免前端引用失效的远程 URL）。"""
    if not messages:
        return
    if not any(m.get("images") for m in messages if isinstance(m, dict)):
        return

    old_by_id = _old_local_by_id(_load_old_messages(int(todo_id)))
    referenced: set[str] = set()

    for m in messages:
        if not isinstance(m, dict):
            continue
        srcs = [u for u in (m.get("images") or []) if isinstance(u, str) and u.strip()]
        if not srcs:
            m["images"] = []
            continue
        mid = str(m.get("id") or "").strip()
        # 已是本地路径（如读缓存后再次走流程）→ 原样保留
        if all(s.startswith("/imges/") for s in srcs):
            m["images"] = srcs
            referenced.update(srcs)
            continue
        # 幂等复用：同一消息 id、张数一致且旧文件都在 → 不重复下载
        reuse = old_by_id.get(mid)
        if reuse and len(reuse) == len(srcs):
            m["images"] = list(reuse)
            referenced.update(reuse)
            continue

        local: List[str] = []
        for u in srcs:
            try:
                data, ct = await asyncio.to_thread(_download, u)
            except Exception as exc:  # noqa: BLE001
                log.warning("[txmsg] 下载消息图片失败 todo_id=%s url=%s: %s", todo_id, u, exc)
                continue
            try:
                ext = _ext_from_url_or_type(u, ct)
                prefix = f"msg_{int(todo_id)}_{mid}" if mid else f"msg_{int(todo_id)}"
                path = save_image_bytes(data, ext=ext, prefix=prefix)
            except Exception as exc:  # noqa: BLE001
                log.warning("[txmsg] 保存消息图片失败 todo_id=%s: %s", todo_id, exc)
                continue
            local.append(path)
        m["images"] = local
        referenced.update(local)

    # 清理不再被引用的旧消息图，避免反复刷新堆积
    for paths in old_by_id.values():
        for p in paths:
            if p not in referenced:
                try:
                    delete_image_file(p)
                except Exception:
                    pass
