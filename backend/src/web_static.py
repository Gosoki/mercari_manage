# -*- coding: utf-8 -*-
"""前端静态资源与兼容健康检查。

- register_health(app)：挂载旧版 /api/health（V2 路径为 /mercariV2/health）。
- mount_spa(app)：将 webside/dist 作为 SPA 挂载到根路径 /。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .app_paths import backend_root
from .readiness import is_ready


def register_health(app: FastAPI) -> None:
    """兼容旧的健康检查路径（部分调用方仍使用 /api/health）。"""

    @app.get("/api/health")
    def health():
        # 仅在系统完全启动后才返回 ok；启动过程中返回 503，避免被误判为就绪。
        if not is_ready():
            return JSONResponse(
                status_code=503,
                content={"status": "starting", "message": "mercari 系统启动中，请稍候"},
            )
        return {"status": "ok", "message": "mercari 订单管理运行中"}


def _webside_dist_dir() -> Path:
    override = (os.environ.get("MERCARI_WEBSIDE_DIST") or "").strip()
    if override:
        return Path(override)
    root = backend_root()
    if getattr(sys, "frozen", False):
        return root / "webside" / "dist"
    # 开发目录：仓库内 webside 与 backend 同级
    return root.parent / "webside" / "dist"


def mount_spa(app: FastAPI) -> None:
    """若存在构建产物且未禁用，则把前端 SPA 挂载到根路径。"""
    spa_dir = _webside_dist_dir()
    if (
        spa_dir.is_dir()
        and os.environ.get("MERCARI_NO_STATIC", "").strip().lower()
        not in ("1", "true", "yes", "on")
    ):
        app.mount(
            "/",
            StaticFiles(directory=str(spa_dir), html=True),
            name="spa",
        )
