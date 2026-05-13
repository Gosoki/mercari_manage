# -*- coding: utf-8 -*-
"""PyInstaller 打包入口：启动 uvicorn，与开发时 ``python -m uvicorn main:app`` 行为一致。"""

from __future__ import annotations

import multiprocessing
import os


def main() -> None:
    multiprocessing.freeze_support()
    port = int(os.environ.get("MERCARI_PORT", "9601"))
    host = os.environ.get("MERCARI_HOST", "0.0.0.0")
    import uvicorn

    from main import app

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
