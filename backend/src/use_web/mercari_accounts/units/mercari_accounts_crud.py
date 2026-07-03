# -*- coding: utf-8 -*-
"""煤炉账号管理 CRUD 端点：列表 / 创建 / 更新 / 删除。"""
import json
import logging
from typing import Optional

from fastapi import HTTPException

from ....db_manage.models.mercari_account import MercariAccountModel
from ...image_storage import delete_image_file
from .mercari_accounts_helpers import (
    _item_api_dict,
    _norm_headers_dict,
    _norm_interval,
    _norm_pause_window,
    _norm_required_text,
    _norm_seller_id,
    _normalize_is_open,
    _validate_status,
)
from .mercari_accounts_models import (
    AUTO_FETCH_TASK_KEYS,
    MercariAccountCreate,
    MercariAccountUpdate,
)

log = logging.getLogger(__name__)

# 「新增账号」预登录共用的 WebDrive 会话键（与前端 MERCARI_PREPARE_KEY 约定一致）
_PREPARE_PROFILE_KEY = "mercari_prepare"


async def _adopt_prepare_login(account_id: int) -> None:
    """把「新增账号」预登录用的 ``mercari_prepare`` profile 迁移为账号主 profile ``mercari_{id}``。

    创建流程中用户在 ``mercari_prepare`` 手动登录煤炉后，登录态只落在该 profile；
    若不迁移，后续同步/抓取从主 profile ``mercari_{id}`` 克隆 Cookie 会读不到登录态，
    用户需在卡片「打开浏览器」重新登录一遍。此处创建成功后把预登录 profile 归属到新账号。

    失败不阻断账号创建（仅记录日志）：用户仍可手动重新登录后再启用账号。
    """
    try:
        from ....web_drive import get_web_drive_manager
        from ....web_drive.core.paths import mercari_account_key

        mgr = get_web_drive_manager()
        moved = await mgr.adopt_profile(_PREPARE_PROFILE_KEY, mercari_account_key(account_id))
        if moved:
            log.info(
                "[mercari_accounts] 已迁移预登录 profile %s → %s",
                _PREPARE_PROFILE_KEY,
                mercari_account_key(account_id),
            )
        else:
            log.info(
                "[mercari_accounts] 无预登录 profile 可迁移（account_id=%s），跳过",
                account_id,
            )
    except Exception as exc:  # noqa: BLE001 迁移失败不应阻断账号创建
        log.warning(
            "[mercari_accounts] 预登录 profile 迁移失败（忽略，可手动重新登录）: %s", exc
        )


def list_mercari_accounts(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    if status:
        _validate_status(status)
    return MercariAccountModel.find_detail_list(
        keyword=keyword,
        status=status,
        page=page,
        page_size=page_size,
    )


def _value_json_for_create(data: MercariAccountCreate) -> str:
    raw = data.value
    if not raw or not isinstance(raw, dict):
        return json.dumps({}, ensure_ascii=False)
    if not any(str(v or "").strip() for v in raw.values()):
        return json.dumps({}, ensure_ascii=False)
    headers = _norm_headers_dict(raw)
    return json.dumps(headers, ensure_ascii=False)


async def create_mercari_account(data: MercariAccountCreate):
    _validate_status(data.status)
    value_json = _value_json_for_create(data)
    name = _norm_required_text(data.account_name, "账号名称")
    lid = (data.login_id or "").strip() or name
    # 每项独立间隔：非空即开启该项；is_open 由是否有任一项开启派生（无总开关）
    intervals = {
        k: _norm_interval(getattr(data, f"auto_fetch_{k}_interval"))
        for k in AUTO_FETCH_TASK_KEYS
    }
    is_open = 1 if any(intervals.values()) else 0
    # 自动上架（售出即补挂）账号级开关：保留用户选择
    rl = 1 if _normalize_is_open(data.auto_fetch_relist) else 0
    pause_s, pause_e = _norm_pause_window(data.pause_start_time, data.pause_end_time)
    kwargs = dict(
        account_name=name,
        login_id=lid,
        seller_id=_norm_seller_id(data.seller_id),
        avatar=(data.avatar or "").strip() or None,
        login_password=None,
        value=value_json,
        status=data.status,
        remark=data.remark,
        is_open=is_open,
        fetch_interval=None,
        auto_fetch_relist=rl,
        pause_start_time=pause_s,
        pause_end_time=pause_e,
    )
    for k in AUTO_FETCH_TASK_KEYS:
        iv = intervals[k]
        kwargs[f"auto_fetch_{k}"] = 1 if iv else 0
        kwargs[f"auto_fetch_{k}_interval"] = iv
    item = MercariAccountModel(**kwargs)
    if not item.save():
        raise HTTPException(status_code=500, detail="保存失败")
    # 把预登录的 mercari_prepare 登录态归属到新账号主 profile，避免创建后需二次登录
    await _adopt_prepare_login(int(item.id))
    return _item_api_dict(item)


def update_mercari_account(aid: int, data: MercariAccountUpdate):
    item = MercariAccountModel.find_by_id(id=aid)
    if not item:
        raise HTTPException(status_code=404, detail="账号不存在")

    if data.account_name is not None:
        item.account_name = _norm_required_text(data.account_name, "账号名称")
    if data.login_id is not None:
        item.login_id = (data.login_id or "").strip() or item.account_name
    if data.seller_id is not None:
        item.seller_id = _norm_seller_id(data.seller_id)
    if data.avatar is not None:
        new_avatar = (data.avatar or "").strip() or None
        old_avatar = (getattr(item, "avatar", None) or "").strip() or None
        # 头像更换：清理旧的本地文件（仅限 /imges/ 内文件）避免残留
        if old_avatar and old_avatar != new_avatar:
            delete_image_file(old_avatar)
        item.avatar = new_avatar
    if data.status is not None:
        _validate_status(data.status)
        item.status = data.status
    if data.remark is not None:
        item.remark = data.remark
    if data.value is not None:
        headers = _norm_headers_dict(data.value)
        item.value = json.dumps(headers, ensure_ascii=False)
    # 每项独立间隔：只要本次提交带了任一 *_interval 字段就按项重算
    intervals_present = any(
        getattr(data, f"auto_fetch_{k}_interval") is not None
        for k in AUTO_FETCH_TASK_KEYS
    )
    if intervals_present:
        for k in AUTO_FETCH_TASK_KEYS:
            raw = getattr(data, f"auto_fetch_{k}_interval")
            cur = getattr(item, f"auto_fetch_{k}_interval", None)
            # raw 为 None 表示本次未携带该项，保留原值；否则规范化（空串=关闭）
            new_iv = _norm_interval(raw) if raw is not None else (cur or None)
            prev_on = bool((cur or "").strip())
            now_on = bool(new_iv)
            setattr(item, f"auto_fetch_{k}_interval", new_iv)
            setattr(item, f"auto_fetch_{k}", 1 if now_on else 0)
            # 新开启（关→开）或关闭时清空该项上次时间：开启后尽快执行、关闭后不残留节流
            if (now_on and not prev_on) or not now_on:
                setattr(item, f"auto_fetch_{k}_last_at", None)
        item.is_open = 1 if any(
            bool((getattr(item, f"auto_fetch_{k}_interval", None) or "").strip())
            for k in AUTO_FETCH_TASK_KEYS
        ) else 0

    # 自动上架账号级开关：独立于各同步项，保留用户选择
    if data.auto_fetch_relist is not None:
        item.auto_fetch_relist = 1 if _normalize_is_open(data.auto_fetch_relist) else 0

    if data.pause_start_time is not None or data.pause_end_time is not None:
        new_start = (
            data.pause_start_time
            if data.pause_start_time is not None
            else getattr(item, "pause_start_time", None)
        )
        new_end = (
            data.pause_end_time
            if data.pause_end_time is not None
            else getattr(item, "pause_end_time", None)
        )
        pause_s, pause_e = _norm_pause_window(new_start, new_end)
        item.pause_start_time = pause_s
        item.pause_end_time = pause_e

    if not item.save():
        raise HTTPException(status_code=500, detail="更新失败")
    return _item_api_dict(item)


def delete_mercari_account(aid: int):
    item = MercariAccountModel.find_by_id(id=aid)
    if not item:
        raise HTTPException(status_code=404, detail="账号不存在")
    avatar = (getattr(item, "avatar", None) or "").strip() or None
    if not item.delete():
        raise HTTPException(status_code=500, detail="删除失败")
    # 账号删除后清理其本地头像文件（仅限 /imges/ 内文件）
    delete_image_file(avatar)
    return {"message": "删除成功"}
