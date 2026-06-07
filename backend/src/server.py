# -*- coding: utf-8 -*-
"""直接运行（不经 nginx）时的 Uvicorn 启动与 TLS 证书解析。

  - 经 nginx 反代：后端跑普通 HTTP，由 nginx 终止 TLS（无需下列任何变量）。
  - 直连端口 / 内网想要 HTTPS：设置下列任一组，让后端自己加载证书提供 https。
优先级：
  1) 显式文件：MERCARI_SSL_CERTFILE + MERCARI_SSL_KEYFILE
  2) 证书文件夹：MERCARI_SSL_CERT_DIR（自动在其中查找常见命名，含 Let's Encrypt
     的 fullchain.pem / privkey.pem）
  3) 都未配置 → 普通 HTTP 启动
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI


def resolve_ssl_config() -> tuple[str | None, str | None]:
    certfile = (os.environ.get("MERCARI_SSL_CERTFILE") or "").strip()
    keyfile = (os.environ.get("MERCARI_SSL_KEYFILE") or "").strip()
    if certfile and keyfile:
        return certfile, keyfile

    cert_dir = (os.environ.get("MERCARI_SSL_CERT_DIR") or "").strip()
    if cert_dir:
        d = Path(cert_dir)
        # 证书（含中间链优先）与私钥的常见文件名
        cert_candidates = [
            "fullchain.pem", "fullchain.cer", "cert.pem",
            "certificate.crt", "server.crt", "server.pem",
        ]
        key_candidates = ["privkey.pem", "private.key", "key.pem", "server.key"]
        found_cert = next((str(d / n) for n in cert_candidates if (d / n).is_file()), None)
        found_key = next((str(d / n) for n in key_candidates if (d / n).is_file()), None)
        if found_cert and found_key:
            return found_cert, found_key
        logging.getLogger(__name__).warning(
            "MERCARI_SSL_CERT_DIR=%s 中未找到匹配的证书/私钥（cert=%s, key=%s），将以 HTTP 启动",
            cert_dir, found_cert, found_key,
        )
    return None, None


def run(app: FastAPI) -> None:
    # PyInstaller 冻结后，子进程会重新执行本入口脚本；freeze_support() 必须在最前调用，
    # 否则每个被 spawn 的子进程都会重新启动整个应用，导致无限循环。
    import multiprocessing

    multiprocessing.freeze_support()

    import uvicorn

    host = (os.environ.get("MERCARI_HOST") or "0.0.0.0").strip()
    port = int((os.environ.get("MERCARI_PORT") or "9601").strip())
    forwarded_allow_ips = (os.environ.get("MERCARI_FORWARDED_ALLOW_IPS") or "127.0.0.1").strip()
    certfile, keyfile = resolve_ssl_config()
    key_password = (os.environ.get("MERCARI_SSL_KEY_PASSWORD") or "").strip() or None

    ssl_kwargs: dict = {}
    if certfile and keyfile:
        ssl_kwargs["ssl_certfile"] = certfile
        ssl_kwargs["ssl_keyfile"] = keyfile
        if key_password:
            ssl_kwargs["ssl_keyfile_password"] = key_password
        print(f"[mercari] HTTPS 直连启动：https://{host}:{port}  (cert={certfile})")
    else:
        print(
            f"[mercari] HTTP 启动：http://{host}:{port}  "
            "(如需后端直连 HTTPS，设置 MERCARI_SSL_CERT_DIR 或 MERCARI_SSL_CERTFILE/MERCARI_SSL_KEYFILE)"
        )

    uvicorn.run(
        app,
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
        **ssl_kwargs,
    )
