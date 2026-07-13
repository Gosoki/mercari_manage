# -*- coding: utf-8 -*-
"""SQLite 方言。

保持项目原有行为逐字一致：WAL、check_same_thread、BEGIN IMMEDIATE、
PRAGMA table_info 内省、方括号标识符、AUTOINCREMENT 建表、旧版删列重建等。
SQLite 是 SQL 的「源语言」，故翻译为恒等（不改写）。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from .base import Dialect


class SqliteDialect(Dialect):
    name = "sqlite"

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ---- 连接与事务 -------------------------------------------------

    def connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)

    def setup(self) -> None:
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=1000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.commit()
        finally:
            conn.close()

    def begin(self, conn) -> None:
        conn.isolation_level = None  # 手动管理事务
        conn.execute("BEGIN IMMEDIATE")

    def commit(self, conn) -> None:
        conn.execute("COMMIT")

    def rollback(self, conn) -> None:
        conn.execute("ROLLBACK")

    # ---- 结构内省 ---------------------------------------------------

    def table_exists(self, executor, table_name: str) -> bool:
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        return len(executor.execute_query(sql, (table_name,))) > 0

    def get_table_columns(self, executor, table_name: str) -> List[Dict[str, Any]]:
        if not self.table_exists(executor, table_name):
            return []
        result = executor.execute_query(f"PRAGMA table_info({table_name})")
        return [
            {'cid': r[0], 'name': r[1], 'type': r[2],
             'notnull': bool(r[3]), 'default_value': r[4], 'pk': bool(r[5])}
            for r in result
        ]

    def get_all_tables(self, executor) -> List[str]:
        sql = ("SELECT name FROM sqlite_master WHERE type='table' "
               "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return [r[0] for r in executor.execute_query(sql)]

    # ---- DDL --------------------------------------------------------

    def create_table(self, executor, table_name: str,
                     columns: List[Dict[str, Any]],
                     indexes: Optional[List[Dict[str, Any]]] = None) -> bool:
        try:
            column_defs = []
            primary_keys = [f'[{col["name"]}]' for col in columns if col.get('primary_key')]

            for col in columns:
                col_name = f'[{col["name"]}]'
                col_def = f"{col_name} {col['type']}"
                if col.get('primary_key') and len(primary_keys) == 1:
                    col_def += " PRIMARY KEY"
                    if col.get('autoincrement'):
                        col_def += " AUTOINCREMENT"
                if col.get('not_null') and not col.get('primary_key'):
                    col_def += " NOT NULL"
                if col.get('unique') and not col.get('primary_key'):
                    col_def += " UNIQUE"
                if col.get('default') is not None:
                    col_def += f" DEFAULT {col['default']}"
                column_defs.append(col_def)

            if len(primary_keys) > 1:
                column_defs.append(f"PRIMARY KEY ({', '.join(primary_keys)})")

            sql = f"CREATE TABLE IF NOT EXISTS [{table_name}] ({', '.join(column_defs)})"
            executor.execute_update(sql)

            if indexes:
                for idx in indexes:
                    idx_name = idx.get('name', f"idx_{table_name}_{idx['columns'][0]}")
                    unique_kw = "UNIQUE " if idx.get('unique') else ""
                    idx_cols = ', '.join([f'[{c}]' for c in idx['columns']])
                    executor.execute_update(
                        f"CREATE {unique_kw}INDEX IF NOT EXISTS {idx_name} "
                        f"ON [{table_name}] ({idx_cols})"
                    )
            return True
        except Exception as e:  # noqa: BLE001
            print(f"创建表 {table_name} 失败: {e}")
            return False

    def add_column(self, executor, table_name: str, column_def: Dict[str, Any]) -> bool:
        try:
            col_sql = f"[{column_def['name']}] {column_def['type']}"
            if column_def.get('not_null'):
                col_sql += " NOT NULL"
            if column_def.get('default') is not None:
                col_sql += f" DEFAULT {column_def['default']}"
            executor.execute_update(f"ALTER TABLE [{table_name}] ADD COLUMN {col_sql}")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"添加列到表 {table_name} 失败: {e}")
            return False

    def drop_column(self, executor, table_name: str, column_name: str) -> bool:
        try:
            version = executor.execute_query("SELECT sqlite_version()")[0][0]
            parts = [int(x) for x in version.split('.')]
            if parts[0] > 3 or (parts[0] == 3 and parts[1] >= 35):
                executor.execute_update(
                    f"ALTER TABLE [{table_name}] DROP COLUMN [{column_name}]")
                return True
            return self._drop_column_recreate_table(executor, table_name, column_name)
        except Exception as e:  # noqa: BLE001
            print(f"删除列 {column_name} 失败: {e}")
            return False

    def _drop_column_recreate_table(self, executor, table_name: str,
                                    column_name: str) -> bool:
        """通过重建表来删除列（旧版 SQLite 兼容）。"""
        try:
            with executor.get_connection() as conn:
                cursor = conn.cursor()
                columns = self.get_table_columns(executor, table_name)
                keep_columns = [col for col in columns if col['name'] != column_name]
                keep_names = [f"[{col['name']}]" for col in keep_columns]
                keep_names_str = ", ".join(keep_names)
                tmp = f"{table_name}_tmp_{abs(hash(column_name)) % 1000000}"

                col_defs = []
                pks = []
                for col in keep_columns:
                    d = f"[{col['name']}] {col['type']}"
                    if col.get('pk'):
                        if sum(1 for c in keep_columns if c.get('pk')) == 1:
                            d += " PRIMARY KEY"
                        else:
                            pks.append(f"[{col['name']}]")
                    if col.get('notnull') and not col.get('pk'):
                        d += " NOT NULL"
                    if col.get('default_value') is not None:
                        d += f" DEFAULT {col['default_value']}"
                    col_defs.append(d)
                if len(pks) > 1:
                    col_defs.append(f"PRIMARY KEY ({', '.join(pks)})")

                cursor.execute(f"CREATE TABLE [{tmp}] ({', '.join(col_defs)})")
                cursor.execute(
                    f"INSERT INTO [{tmp}] ({keep_names_str}) "
                    f"SELECT {keep_names_str} FROM [{table_name}]")
                cursor.execute(f"DROP TABLE [{table_name}]")
                cursor.execute(f"ALTER TABLE [{tmp}] RENAME TO [{table_name}]")
                conn.commit()
                return True
        except Exception as e:  # noqa: BLE001
            print(f"重建表删除列失败: {e}")
            return False

    # ---- JSON --------------------------------------------------------

    def json_array_each(self, json_col_expr: str, alias: str) -> str:
        return f"json_each({json_col_expr}) {alias}"

    def json_array_each_text(self, json_col_expr: str, alias: str) -> str:
        return f"json_each({json_col_expr}) {alias}"

    def json_extract_int(self, value_expr: str, key: str) -> str:
        return f"CAST(json_extract({value_expr}, '$.{key}') AS INTEGER)"

    def greatest(self, *exprs: str) -> str:
        return f"MAX({', '.join(exprs)})"

    def table_source(self, table_expr: str, alias: str, materialize: bool = False) -> str:
        return f"{table_expr} {alias}"
