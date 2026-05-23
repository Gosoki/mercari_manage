# -*- coding: utf-8 -*-
"""代办事项同步入口（HTTP 层）。"""

from typing import Any, Dict

from fastapi import HTTPException

from ....db_manage.models.todo_item import TodoItemModel
from ....use_mercari.get_to_du_list.todolist_sync import (
    _resolve_account_id,
    sync_todos_from_mercari,
)
from ....use_mercari.get_to_du_list.transaction_detail import (
    fetch_transaction_detail,
)
from ....web_drive.core.account_serial_queue import (
    queue_key_for_meilu_account,
    run_meilu_serial_async,
)
from .todos_models import SyncTodosRequest


async def sync_todos(req: SyncTodosRequest) -> Dict[str, Any]:
    """从煤炉同步当前账号的代办事项；按账号串行避免浏览器抢占。"""
    try:
        aid = _resolve_account_id(req.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stats = await run_meilu_serial_async(
        queue_key_for_meilu_account(aid),
        lambda: sync_todos_from_mercari(account_id=aid),
    )
    return stats


async def fetch_todo_transaction_detail(todo_id: int) -> Dict[str, Any]:
    """处理按钮：打开 transaction 页 → 提取 DOM 字段 → 返回；浏览器保持打开。"""
    todo = TodoItemModel.find_by_id(id=int(todo_id))
    if not todo:
        raise HTTPException(status_code=404, detail="代办事项不存在")
    aid = int(getattr(todo, "account_id", 0) or 0)
    if not aid:
        raise HTTPException(status_code=400, detail="代办事项缺少 account_id")

    try:
        data = await run_meilu_serial_async(
            queue_key_for_meilu_account(aid),
            lambda: fetch_transaction_detail(int(todo_id)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return data
