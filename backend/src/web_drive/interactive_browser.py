# -*- coding: utf-8 -*-
"""
煤炉账号页「打开浏览器」：为每个活跃账号启动有头 Edge（profile ``meilu_{id}``）。

与前端 ``webDriveApi.openSession({ account_key: meilu_{id}, headless: false, start_url })`` 一致。
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MERCARI_HOME = "https://jp.mercari.com/"


async def startup_interactive_browsers_for_all_active_accounts() -> None:
    """
    系统启动时调用：为数据库中所有 status='active' 的煤炉账号打开有头浏览器。

    - 顺序逐个启动，避免同时抢占 profile 目录锁
    - 单个账号失败只记警告，不影响其它账号及 HTTP 服务启动
    """
    try:
        from ..db_manage.database import DatabaseManager
        from .paths import meilu_account_key
        from .manager import get_web_drive_manager

        db = DatabaseManager()
        rows = db.execute_query(
            "SELECT [id] FROM [meilu_accounts] WHERE LOWER(TRIM([status])) = 'active' ORDER BY [id]"
        )
        account_ids = [int(r[0]) for r in rows]
    except Exception as exc:
        log.warning(
            "startup_interactive_browsers: 读取活跃账号列表失败，跳过有头浏览器预启动: %s",
            exc,
        )
        return

    if not account_ids:
        log.info("startup_interactive_browsers: 无活跃煤炉账号，跳过有头浏览器预启动")
        return

    mgr = get_web_drive_manager()
    log.info(
        "startup_interactive_browsers: 开始为 %d 个活跃账号打开有头 Edge %s",
        len(account_ids),
        account_ids,
    )
    for aid in account_ids:
        key = meilu_account_key(aid)
        try:
            result = await mgr.open_session(
                key,
                headless=False,
                start_url=MERCARI_HOME,
                interactive=True,
            )
            log.info(
                "startup_interactive_browsers: account_id=%d key=%s already_running=%s",
                aid,
                key,
                result.get("already_running"),
            )
        except Exception as exc:
            log.warning(
                "startup_interactive_browsers: 账号 %d 有头浏览器启动失败（可在煤炉账号页手动打开）: %s",
                aid,
                exc,
            )

    log.info("startup_interactive_browsers: 有头浏览器预启动完成")
