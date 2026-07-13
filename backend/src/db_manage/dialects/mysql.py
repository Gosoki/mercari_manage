# -*- coding: utf-8 -*-
"""MySQL 8.0+ 方言（PyMySQL 驱动）。

要点：
  · 连接由「翻译包装器」返回，其 cursor 在 execute/executemany 前把 SQLite 风格
    SQL（``?`` 占位符、``[标识符]`` 方括号）翻译为 MySQL 语法。这样
    DatabaseManager 内部调用与散落各处的 ``conn.cursor().execute`` 同时受益，
    上层 262 处调用点无需改动。
  · 轻量线程安全连接池，避免每次操作都重建连接。
  · TEXT 列按用途映射：被索引/唯一/带默认值的短字符串→VARCHAR(255)，
    其余长文本（Base64 图片、JSON 等）→LONGTEXT（MySQL 不允许对 TEXT 直接
    建索引、也不允许其带字面默认值）。
"""

from __future__ import annotations

import os
import queue
import threading
from typing import Any, Dict, List, Optional

from .base import Dialect
from ._translate import translate

try:  # 延迟导入：仅在选用 mysql 后端时才需要 PyMySQL
    import pymysql
except Exception:  # noqa: BLE001
    pymysql = None


# ---------------------------------------------------------------------------
# 翻译包装器：让 cursor.execute / executemany 自动翻译 SQL
# ---------------------------------------------------------------------------

class _TranslatingCursor:
    def __init__(self, raw_cursor):
        self._c = raw_cursor

    def execute(self, sql, params=None):
        return self._c.execute(translate(sql, params is not None), params)

    def executemany(self, sql, params_list):
        return self._c.executemany(translate(sql, True), params_list)

    def __getattr__(self, name):
        return getattr(self._c, name)

    def __iter__(self):
        return iter(self._c)

    def __enter__(self):
        self._c.__enter__()
        return self

    def __exit__(self, *exc):
        return self._c.__exit__(*exc)


class _TranslatingConnection:
    """包装 PyMySQL 连接：cursor 自动翻译；close() 归还连接池而非真正关闭。"""

    def __init__(self, raw_conn, pool):
        self._conn = raw_conn
        self._pool = pool

    def cursor(self, *a, **kw):
        return _TranslatingCursor(self._conn.cursor(*a, **kw))

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def begin(self):
        self._conn.begin()

    def close(self):
        # 归还连接池；池满或连接失效则真正关闭
        self._pool.release(self._conn)

    @property
    def raw(self):
        return self._conn

    def __getattr__(self, name):
        return getattr(self._conn, name)


# ---------------------------------------------------------------------------
# 轻量连接池
# ---------------------------------------------------------------------------

class _Pool:
    def __init__(self, connect_fn, maxsize: int):
        self._connect = connect_fn
        self._q: "queue.Queue" = queue.Queue(maxsize)

    def acquire(self):
        try:
            conn = self._q.get_nowait()
        except queue.Empty:
            return self._connect()
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            return self._connect()

    def release(self, conn) -> None:
        try:
            self._q.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# 方言
# ---------------------------------------------------------------------------

class MysqlDialect(Dialect):
    name = "mysql"

    def __init__(self):
        if pymysql is None:
            raise RuntimeError(
                "选用 DB_BACKEND=mysql 但未安装 PyMySQL，请先 pip install PyMySQL")
        self.host = os.environ.get("MYSQL_HOST", "127.0.0.1")
        self.port = int(os.environ.get("MYSQL_PORT", "3306"))
        self.user = os.environ.get("MYSQL_USER", "root")
        self.password = os.environ.get("MYSQL_PASSWORD", "")
        self.database = os.environ.get("MYSQL_DATABASE", "mercari")
        self._pool_size = int(os.environ.get("MYSQL_POOL_SIZE", "10"))
        self._pool = _Pool(self._raw_connect, self._pool_size)

    def _raw_connect(self):
        return pymysql.connect(
            host=self.host, port=self.port, user=self.user,
            password=self.password, database=self.database,
            charset="utf8mb4", autocommit=False,
        )

    # ---- 连接与事务 -------------------------------------------------

    def connect(self):
        return _TranslatingConnection(self._pool.acquire(), self._pool)

    def setup(self) -> None:
        # 确保目标库存在（用不带 database 的连接创建），随后建立连接池
        conn = pymysql.connect(
            host=self.host, port=self.port, user=self.user,
            password=self.password, charset="utf8mb4", autocommit=True,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            conn.close()

    def begin(self, conn) -> None:
        conn.begin()

    def commit(self, conn) -> None:
        conn.commit()

    def rollback(self, conn) -> None:
        conn.rollback()

    # ---- 结构内省 ---------------------------------------------------

    def table_exists(self, executor, table_name: str) -> bool:
        rows = executor.execute_query(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ? LIMIT 1",
            (self.database, table_name),
        )
        return len(rows) > 0

    def get_table_columns(self, executor, table_name: str) -> List[Dict[str, Any]]:
        rows = executor.execute_query(
            "SELECT ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
            "COLUMN_DEFAULT, COLUMN_KEY FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ORDINAL_POSITION",
            (self.database, table_name),
        )
        return [
            {'cid': (r[0] or 1) - 1, 'name': r[1], 'type': r[2],
             'notnull': (str(r[3]).upper() == 'NO'),
             'default_value': r[4], 'pk': (str(r[5]).upper() == 'PRI')}
            for r in rows
        ]

    def get_all_tables(self, executor) -> List[str]:
        rows = executor.execute_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = ? AND table_type = 'BASE TABLE' "
            "ORDER BY table_name",
            (self.database,),
        )
        return [r[0] for r in rows]

    def _index_exists(self, executor, table_name: str, index_name: str) -> bool:
        rows = executor.execute_query(
            "SELECT 1 FROM information_schema.statistics "
            "WHERE table_schema = ? AND table_name = ? AND index_name = ? LIMIT 1",
            (self.database, table_name, index_name),
        )
        return len(rows) > 0

    # ---- 类型映射 ---------------------------------------------------

    @staticmethod
    def _format_default(value: Any) -> str:
        """把模型里的默认值转为合法的 MySQL 字面量。

        兼容项目里两种历史写法：已内嵌引号的（``"'new_unused'"``）与未加引号的
        裸字符串（``'默认仓库'``，SQLite 宽容接受但 MySQL 需显式加引号）。
        数字、``NULL``、``CURRENT_TIMESTAMP`` 等关键字原样输出。
        """
        s = str(value).strip()
        if s == "":
            return "''"
        up = s.upper()
        if up in ("CURRENT_TIMESTAMP", "NULL", "TRUE", "FALSE"):
            return s
        if (s[0] == "'" and s[-1] == "'") or (s[0] == '"' and s[-1] == '"'):
            return s
        try:
            float(s)
            return s
        except ValueError:
            return "'" + s.replace("'", "''") + "'"

    @staticmethod
    def _map_type(col: Dict[str, Any], indexed_names: set) -> str:
        t = str(col.get('type', 'TEXT')).upper()
        if 'INT' in t:
            if col.get('primary_key') and col.get('autoincrement'):
                return 'BIGINT'
            return 'INT'
        if t in ('REAL', 'FLOAT', 'DOUBLE') or 'FLOA' in t or 'DOUB' in t:
            return 'DOUBLE'
        if 'DATETIME' in t or 'TIMESTAMP' in t:
            return 'DATETIME'
        if 'DATE' in t:
            return 'DATE'
        # TEXT / CHAR 等文本
        short = (col.get('unique') or col.get('name') in indexed_names
                 or col.get('default') is not None)
        return 'VARCHAR(255)' if short else 'LONGTEXT'

    # ---- DDL --------------------------------------------------------

    def create_table(self, executor, table_name: str,
                     columns: List[Dict[str, Any]],
                     indexes: Optional[List[Dict[str, Any]]] = None) -> bool:
        try:
            indexed = self._indexed_column_names(indexes)
            primary_keys = [col['name'] for col in columns if col.get('primary_key')]
            defs: List[str] = []
            for col in columns:
                typ = self._map_type(col, indexed)
                d = f"`{col['name']}` {typ}"
                is_pk = col.get('primary_key')
                if (is_pk and len(primary_keys) == 1) or col.get('not_null'):
                    d += " NOT NULL"
                if is_pk and col.get('autoincrement') and len(primary_keys) == 1:
                    d += " AUTO_INCREMENT"
                if col.get('unique') and not is_pk:
                    d += " UNIQUE"
                if col.get('default') is not None:
                    d += f" DEFAULT {self._format_default(col['default'])}"
                defs.append(d)
            if primary_keys:
                pk_cols = ', '.join(f"`{c}`" for c in primary_keys)
                defs.append(f"PRIMARY KEY ({pk_cols})")

            sql = (f"CREATE TABLE IF NOT EXISTS `{table_name}` ({', '.join(defs)}) "
                   "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
                   "COLLATE=utf8mb4_unicode_ci")
            executor.execute_update(sql)

            for idx in (indexes or []):
                idx_name = idx.get('name', f"idx_{table_name}_{idx['columns'][0]}")
                if self._index_exists(executor, table_name, idx_name):
                    continue
                unique_kw = "UNIQUE " if idx.get('unique') else ""
                idx_cols = ', '.join(f"`{c}`" for c in idx['columns'])
                executor.execute_update(
                    f"CREATE {unique_kw}INDEX `{idx_name}` "
                    f"ON `{table_name}` ({idx_cols})"
                )
            return True
        except Exception as e:  # noqa: BLE001
            print(f"创建表 {table_name} 失败: {e}")
            return False

    @staticmethod
    def _indexed_column_names(indexes: Optional[List[Dict[str, Any]]]) -> set:
        names = set()
        for idx in (indexes or []):
            for c in idx.get('columns', []):
                names.add(c)
        return names

    def add_column(self, executor, table_name: str, column_def: Dict[str, Any]) -> bool:
        try:
            typ = self._map_type(column_def, set())
            col_sql = f"`{column_def['name']}` {typ}"
            if column_def.get('not_null'):
                col_sql += " NOT NULL"
            if column_def.get('default') is not None:
                col_sql += f" DEFAULT {self._format_default(column_def['default'])}"
            executor.execute_update(
                f"ALTER TABLE `{table_name}` ADD COLUMN {col_sql}")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"添加列到表 {table_name} 失败: {e}")
            return False

    def drop_column(self, executor, table_name: str, column_name: str) -> bool:
        try:
            executor.execute_update(
                f"ALTER TABLE `{table_name}` DROP COLUMN `{column_name}`")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"删除列 {column_name} 失败: {e}")
            return False

    def drop_table(self, executor, table_name: str) -> bool:
        try:
            executor.execute_update(f"DROP TABLE IF EXISTS `{table_name}`")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"删除表 {table_name} 失败: {e}")
            return False

    # ---- JSON --------------------------------------------------------

    def json_array_each(self, json_col_expr: str, alias: str) -> str:
        # 把 JSON 数组按元素展开；value 列取每个元素的完整 JSON（对象或标量）
        return (f"JSON_TABLE({json_col_expr}, '$[*]' "
                f"COLUMNS(value JSON PATH '$')) {alias}")

    def json_array_each_text(self, json_col_expr: str, alias: str) -> str:
        # 标量字符串数组：以 VARCHAR 取值，自动去掉 JSON 引号
        return (f"JSON_TABLE({json_col_expr}, '$[*]' "
                f"COLUMNS(value VARCHAR(4096) PATH '$')) {alias}")

    def json_extract_int(self, value_expr: str, key: str) -> str:
        return f"CAST(JSON_EXTRACT({value_expr}, '$.{key}') AS SIGNED)"
