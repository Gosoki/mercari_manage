# -*- coding: utf-8 -*-
"""数据库管理处理器：查看当前后端 / 测试 MySQL 连接 / 切换后端（含数据迁移 + 重启）。

约定：默认 SQLite；可切到 MySQL。切换时把当前库数据迁移到目标库，成功后持久化选择并
自动重启后端生效。SQLite 始终保留，仅存 bootstrap 系统配置（见 db_manage/db_settings.py）。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from ....app_paths import backend_root_str
from ....db_manage import db_settings
from ....db_manage import migrate as migrator
from ....db_manage.db_manager import get_db_manager
from ....system_service import resolve_restart_bat, schedule_restart_via_bat


class MysqlParams(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: Optional[str] = None  # 为空则沿用已保存的密码
    database: str = "mercari"


class MysqlParamsOut(BaseModel):
    host: str
    port: int
    user: str
    database: str
    password_set: bool  # 不回传明文密码，仅告知是否已配置


class DbConfigOut(BaseModel):
    backend: str
    mysql: MysqlParamsOut


class TestResult(BaseModel):
    ok: bool
    version: Optional[str] = None
    database_exists: Optional[bool] = None
    message: str = ""


class SwitchIn(BaseModel):
    backend: str                      # 'sqlite' | 'mysql'
    mysql: Optional[MysqlParams] = None


class SwitchOut(BaseModel):
    ok: bool
    message: str
    tables: List[Dict[str, Any]] = []
    restarting: bool = False


def get_database_config() -> DbConfigOut:
    m = db_settings.get_mysql_config()
    return DbConfigOut(
        backend=db_settings.get_active_backend(),
        mysql=MysqlParamsOut(
            host=m["host"], port=m["port"], user=m["user"],
            database=m["database"], password_set=bool(m["password"]),
        ),
    )


def _resolve_password(params: MysqlParams) -> str:
    """密码为空时沿用已保存的密码，避免前端每次都要重填。"""
    if params.password:
        return params.password
    return db_settings.get_mysql_config().get("password", "")


def test_mysql_connection(params: MysqlParams) -> TestResult:
    try:
        import pymysql
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="服务器未安装 PyMySQL")
    pw = _resolve_password(params)
    try:
        conn = pymysql.connect(
            host=params.host, port=int(params.port), user=params.user,
            password=pw, charset="utf8mb4", connect_timeout=8, autocommit=True,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"连接失败：{e}")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (params.database,),
            )
            exists = bool(cur.fetchone())
    finally:
        conn.close()
    return TestResult(ok=True, version=str(version), database_exists=exists,
                      message="连接成功")


def _build_target_dialect(backend: str, params: Optional[MysqlParams]):
    if backend == "mysql":
        if params is None:
            raise HTTPException(status_code=400, detail="切换到 MySQL 需提供连接参数")
        from ....db_manage.dialects.mysql import MysqlDialect
        return MysqlDialect({
            "host": params.host, "port": int(params.port), "user": params.user,
            "password": _resolve_password(params), "database": params.database,
        })
    from ....db_manage.dialects.sqlite import SqliteDialect
    return SqliteDialect(os.path.join(backend_root_str(), "mercariDB.db"))


async def switch_database(body: SwitchIn) -> SwitchOut:
    if body.backend not in ("sqlite", "mysql"):
        raise HTTPException(status_code=400, detail=f"未知后端：{body.backend}")

    current = db_settings.get_active_backend()
    if body.backend == current:
        raise HTTPException(status_code=400, detail=f"当前已在使用 {current}，无需切换")

    # 切到 MySQL 前先验证连接
    if body.backend == "mysql":
        test_mysql_connection(body.mysql or MysqlParams())

    mgr = get_db_manager()
    source_db = mgr.db            # 当前运行的 DatabaseManager（后端无关）
    target_dialect = _build_target_dialect(body.backend, body.mysql)

    # 建目标库结构 + 迁移全部数据（逐表校验行数）
    try:
        result = migrator.migrate(source_db, target_dialect, mgr.models)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"数据迁移失败：{e}")
    if not result["ok"]:
        bad = ", ".join(s["table"] for s in result["mismatch"])
        raise HTTPException(status_code=500, detail=f"迁移后行数不一致：{bad}")

    # 迁移成功 → 持久化后端选择
    mysql_cfg = None
    if body.backend == "mysql":
        p = body.mysql
        mysql_cfg = {"host": p.host, "port": int(p.port), "user": p.user,
                     "password": _resolve_password(p), "database": p.database}
    db_settings.save_db_config(body.backend, mysql_cfg)

    # 自动重启后端生效（打包态走 restart.bat；开发态提示手动重启）
    if resolve_restart_bat() is not None:
        asyncio.create_task(schedule_restart_via_bat(delay_seconds=1.0))
        msg = f"已迁移到 {body.backend} 并保存配置，正在重启后端，请约 10 秒后刷新页面"
        restarting = True
    else:
        msg = f"已迁移到 {body.backend} 并保存配置，请手动重启后端生效"
        restarting = False

    return SwitchOut(ok=True, message=msg, tables=result["tables"],
                     restarting=restarting)
