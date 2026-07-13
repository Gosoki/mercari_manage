# -*- coding: utf-8 -*-
"""后端间数据迁移：在 SQLite 与 MySQL 之间建表并拷贝全部业务数据。

设计：源库用当前运行的 ``DatabaseManager``（后端无关，写 SQLite 风格 SQL 即可）；
目标库用一个「新建的 dialect 实例」配上最小执行器 ``_TargetExecutor``，从而与
``DatabaseManager`` 单例解耦——迁移期间同时操作「当前库（源）」与「目标库」。

供两处复用：数据库管理页的切换动作、命令行 tools/sqlite_to_mysql.py。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, List

BATCH = 500


class _TargetExecutor:
    """最小执行器：给定一个 dialect，提供其 DDL/内省/写入所需的 execute_* 与 get_connection，
    独立于 DatabaseManager 单例（用于操作迁移「目标库」）。"""

    def __init__(self, dialect):
        self.dialect = dialect

    @contextmanager
    def get_connection(self):
        conn = self.dialect.connect()
        try:
            yield conn
        finally:
            conn.close()

    def execute_query(self, sql: str, params: tuple = ()) -> List[tuple]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

    def execute_update(self, sql: str, params: tuple = ()) -> int:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount

    def execute_many(self, sql: str, params_list: List[tuple]) -> int:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(sql, params_list)
            conn.commit()
            return cur.rowcount

    # DDL / 内省委托给 dialect
    def table_exists(self, table: str) -> bool:
        return self.dialect.table_exists(self, table)

    def get_table_columns(self, table: str) -> List[Dict[str, Any]]:
        return self.dialect.get_table_columns(self, table)

    def create_table(self, table, columns, indexes=None) -> bool:
        return self.dialect.create_table(self, table, columns, indexes)


def _model_columns(model) -> List[Dict[str, Any]]:
    return [
        {
            'name': fname,
            'type': fdef['type'],
            'primary_key': fdef.get('primary_key', False),
            'autoincrement': fdef.get('autoincrement', False),
            'not_null': fdef.get('not_null', False),
            'unique': fdef.get('unique', False),
            'default': fdef.get('default'),
            'max_length': fdef.get('max_length'),
            'mysql_type': fdef.get('mysql_type'),
        }
        for fname, fdef in model.get_fields().items()
    ]


def build_target_schema(target: _TargetExecutor, models) -> None:
    """按模型定义在目标库建出全部表（幂等：CREATE TABLE IF NOT EXISTS）。"""
    for model in models:
        target.create_table(model.get_table_name(), _model_columns(model),
                            model.get_indexes())


def copy_all_data(source_db, target: _TargetExecutor, models) -> List[Dict[str, Any]]:
    """把源库各表数据拷入目标库（仅拷两侧都存在的列，先清空目标表）。返回逐表统计。"""
    summary: List[Dict[str, Any]] = []
    for model in models:
        table = model.get_table_name()
        if not source_db.table_exists(table):
            summary.append({"table": table, "src": 0, "dst": 0, "status": "源无此表"})
            continue
        tgt_cols = {c["name"] for c in target.get_table_columns(table)}
        src_cols = [c["name"] for c in source_db.get_table_columns(table)]
        cols = [c for c in src_cols if c in tgt_cols]
        if not cols:
            summary.append({"table": table, "src": 0, "dst": 0, "status": "无公共列"})
            continue

        target.execute_update(f"DELETE FROM [{table}]")
        col_sql = ", ".join(f"[{c}]" for c in cols)
        ph = ", ".join(["?"] * len(cols))
        insert_sql = f"INSERT INTO [{table}] ({col_sql}) VALUES ({ph})"

        rows = source_db.execute_query(f"SELECT {col_sql} FROM [{table}]")
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            target.execute_many(insert_sql, [tuple(r) for r in chunk])

        src_count = source_db.execute_query(f"SELECT COUNT(*) FROM [{table}]")[0][0]
        dst_count = target.execute_query(f"SELECT COUNT(*) FROM [{table}]")[0][0]
        summary.append({
            "table": table, "src": int(src_count), "dst": int(dst_count),
            "status": "OK" if src_count == dst_count else "行数不一致",
        })
    return summary


def migrate(source_db, target_dialect, models) -> Dict[str, Any]:
    """在目标库建表并从源库拷贝全部数据，返回 {ok, tables, mismatch}。"""
    target = _TargetExecutor(target_dialect)
    target_dialect.setup()
    build_target_schema(target, models)
    summary = copy_all_data(source_db, target, models)
    mismatch = [s for s in summary if s["status"] == "行数不一致"]
    return {"ok": not mismatch, "tables": summary, "mismatch": mismatch}
