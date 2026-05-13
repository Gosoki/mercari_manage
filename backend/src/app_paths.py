# -*- coding: utf-8 -*-
"""开发与 PyInstaller 冻结后的 backend 根目录（exe 同目录即数据与静态资源根）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def backend_root() -> Path:
    override = (os.environ.get("MERCARI_BACKEND_ROOT") or "").strip()
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # backend/src/app_paths.py → backend/
    return Path(__file__).resolve().parents[1]


def backend_root_str() -> str:
    return str(backend_root())
