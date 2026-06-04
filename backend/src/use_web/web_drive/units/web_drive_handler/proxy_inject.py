# -*- coding: utf-8 -*-
"""Cookie 注入端点：把账号登录态注入 mercari-proxy，供用户本地浏览器访问。

流程：读取服务端 profile 的煤炉 Cookie → 暂存到 Node 反代（一次性 token）→
返回引导地址（<base>/__boot?token=...）。前端用 window.open 在用户本地浏览器打开。
"""
import secrets

from fastapi import HTTPException
from pydantic import BaseModel as PydanticModel, Field

from .....web_drive import get_web_drive_manager
from .....mercari_proxy import (
    boot_path,
    is_running,
    proxy_port,
    proxy_scheme,
    register_injection,
    start_proxy,
)


class InjectCookiesBody(PydanticModel):
    account_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )


async def inject_cookies(body: InjectCookiesBody):
    if not is_running():
        r = start_proxy()
        if not r.get("running"):
            raise HTTPException(
                status_code=500,
                detail=r.get("error") or "mercari-proxy 未启动",
            )
    try:
        cookies = await get_web_drive_manager().export_cookies(body.account_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not cookies:
        raise HTTPException(
            status_code=400,
            detail="未读取到该账号的登录 Cookie，请先打开浏览器登录 jp.mercari.com。",
        )

    token = secrets.token_urlsafe(24)
    try:
        register_injection(token, cookies)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Cookie 注入失败: {exc}") from exc

    return {
        "success": True,
        "data": {
            "boot_path": boot_path(token),
            "scheme": proxy_scheme(),
            "port": proxy_port(),
            "count": len(cookies),
        },
    }
