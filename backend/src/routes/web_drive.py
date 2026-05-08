# -*- coding: utf-8 -*-
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as PydanticModel, Field

from ..web_drive import get_web_drive_manager, profiles_root

router = APIRouter(prefix="/api/web-drive", tags=["web-drive"])
log = logging.getLogger(__name__)


class OpenSessionBody(PydanticModel):
    """启动指定账号的 Edge 子浏览器（独立 profile，Cookie 持久化在服务端目录）。"""

    account_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    headless: bool = False
    start_url: Optional[str] = None
    use_mitm_proxy: bool = False
    mitm_proxy_url: Optional[str] = None


class CloseSessionBody(PydanticModel):
    account_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )


@router.get("/profiles-root")
def get_profiles_root():
    """返回当前 profile 根目录（环境变量 WEB_DRIVE_PROFILES_DIR 可覆盖）。"""
    return {"profiles_root": profiles_root()}


@router.get("/sessions")
async def list_sessions():
    return {"sessions": get_web_drive_manager().list_sessions()}


@router.post("/sessions/open")
async def open_session(body: OpenSessionBody):
    try:
        proxy = None
        if body.use_mitm_proxy:
            from ..ssl_mitm_proxy.runner import default_mitm_proxy_url

            proxy = (body.mitm_proxy_url or "").strip() or default_mitm_proxy_url()
        return {
            "success": True,
            "data": await get_web_drive_manager().open_session(
                body.account_key,
                headless=body.headless,
                start_url=body.start_url,
                proxy_server=proxy,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sessions/close")
async def close_session(body: CloseSessionBody):
    try:
        return {"success": True, "data": await get_web_drive_manager().close_session(body.account_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ──────────────────────── 出品自动化 ──────────────────────── #

class PostToMarketBody(PydanticModel):
    """
    出品自动化请求体。

    account_key  : webdrive 账号标识（通常为 meilu_{id}）
    name         : 商品名称
    description  : 商品说明（已含管理番号行）
    image_urls   : 图片路径列表（/imges/xxx.jpg 或外部 URL）
    proxy_server : MITM 代理地址；留空则用默认值 http://127.0.0.1:8890
    use_mitm_proxy: 是否启用 MITM 代理（默认 True）
    """

    account_key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = ""
    description: str = ""
    image_urls: List[str] = []
    proxy_server: Optional[str] = None
    use_mitm_proxy: bool = True


@router.post("/listing/post-to-market")
async def post_to_market(body: PostToMarketBody):
    """
    启动（或复用）指定账号的 Edge 持久化会话（SSL 中间人代理），
    导航到 https://jp.mercari.com/sell/create，并自动完成：
      · 图片上传（写真を追加）
      · 商品名称填写
      · 商品说明填写
    """
    from ..web_drive.web_operate.post_to_macket import post_to_market as _do_post
    from ..ssl_mitm_proxy.runner import default_mitm_proxy_url

    try:
        proxy: Optional[str] = None
        if body.use_mitm_proxy:
            proxy = (body.proxy_server or "").strip() or default_mitm_proxy_url()

        data = await _do_post(
            get_web_drive_manager(),
            body.account_key,
            name=body.name,
            description=body.description,
            image_urls=body.image_urls,
            proxy_server=proxy,
        )
        return {"success": True, "data": data}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("post_to_market 异常")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
