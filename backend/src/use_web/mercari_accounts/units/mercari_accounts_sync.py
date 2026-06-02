# -*- coding: utf-8 -*-
"""单账号「同步数据」：一键同步指定账号在各业务页面的数据。

账号管理页每张账号卡片的「同步数据」按钮调用本入口：对**单个**账号依次同步
待办 / 通知 / 在售商品 / 订单列表 / 订单状态，全部在该账号的串行队列内顺序执行，
完成后关闭其浏览器。某一步失败不影响其余步骤（错误汇总在 errors 中返回）。

注意：各业务页的「从煤炉同步」按钮现在会一键同步**全部已开启账号**；本入口与其
互补，用于只同步某一个账号。
"""

import logging
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from ....db_manage.models.mercari_account import MercariAccountModel
from ....web_drive.core.account_serial_queue import (
    queue_key_for_mercari_account,
    run_mercari_serial_async,
)
from ....web_drive.core.manager import get_web_drive_manager
from ....web_drive.core.paths import mercari_account_key
from ....use_mercari.get_to_du_list.todolist_sync import sync_todos_from_mercari
from ....use_mercari.get_notifications.notification_sync import (
    sync_notifications_from_mercari,
)
from ....use_mercari.on_sale_items_sync import sync_on_sale_items_from_mercari
from ....use_mercari.sync_data import batch_refresh_orders_info, sync_new_data
from ....use_mercari.sync_progress import clear_sync_progress, set_sync_progress_page

log = logging.getLogger(__name__)

# 与各同步入口一致的安全字符集，避免路径注入
_SYNC_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,128}$")


class SyncAccountDataRequest(BaseModel):
    progress_job_id: Optional[str] = None


async def sync_account_all_data(aid: int, req: SyncAccountDataRequest) -> Dict[str, Any]:
    """同步单个账号在「待办 / 通知 / 在售 / 订单列表 / 订单状态」各页面的数据。

    所有步骤在该账号的串行队列内顺序执行（一个完成后才进行下一个），结束后关闭浏览器。
    """
    account_id = int(aid)
    account = MercariAccountModel.find_by_id(id=account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"煤炉账号 id={account_id} 不存在")

    jid = (req.progress_job_id or "").strip() or None
    if jid and not _SYNC_JOB_ID_RE.fullmatch(jid):
        raise HTTPException(status_code=400, detail="invalid progress_job_id")

    # (key, 中文名, 构造协程的工厂)；每步都接入该账号的进度上报
    steps = [
        ("todos", "待办事项", lambda: sync_todos_from_mercari(account_id=account_id, progress_job_id=jid)),
        ("notifications", "通知", lambda: sync_notifications_from_mercari(account_id=account_id, progress_job_id=jid)),
        ("on_sale", "在售商品", lambda: sync_on_sale_items_from_mercari(account_id=account_id, progress_job_id=jid)),
        ("orders_list", "订单列表", lambda: sync_new_data(account_id=account_id, progress_job_id=jid)),
        ("orders_status", "订单状态", lambda: batch_refresh_orders_info(account_id=account_id, progress_job_id=jid)),
    ]

    qk = queue_key_for_mercari_account(account_id)
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    try:
        for key, _label, factory in steps:
            try:
                results[key] = await run_mercari_serial_async(
                    qk,
                    factory,
                    suppress_idle_close=True,  # 多步复用同一浏览器，全部完成后再统一关闭
                )
            except Exception as exc:  # noqa: BLE001 单步失败不影响其余步骤
                errors[key] = str(exc)
                log.warning(
                    "[account-sync] account_id=%s step=%s 失败: %s", account_id, key, exc
                )
    finally:
        # 全部步骤完成后关闭该账号浏览器（各步以 suppress_idle_close 跳过了自动关闭）。
        try:
            mgr = get_web_drive_manager()
            await mgr.close_session(mercari_account_key(account_id), force=True)
        except Exception as close_exc:  # noqa: BLE001
            log.warning(
                "[account-sync] 关闭 account_id=%s 浏览器失败: %s", account_id, close_exc
            )
        if jid:
            # 在售同步用的进度存储与通用 sync_progress 是同一份，clear 一次即可。
            clear_sync_progress(jid)

    return {
        "success": True,
        "data": {
            "account_id": account_id,
            "account_name": account.account_name,
            "ok_count": len(results),
            "fail_count": len(errors),
            "results": results,
            "errors": errors,
        },
    }
