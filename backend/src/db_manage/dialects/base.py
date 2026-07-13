# -*- coding: utf-8 -*-
"""数据库方言基类。

方言层封装了不同数据库（SQLite / MySQL）之间的全部差异：
连接与事务、DDL 生成（建表/加列/删列）、结构内省，以及 SQL 语法翻译。
上层 DatabaseManager 与所有 Model 仅面向本接口，写一种 SQLite 风格
（``?`` 占位符、``[标识符]`` 方括号引用），由具体方言在执行时按需翻译。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Dialect(ABC):
    """抽象方言：定义 DatabaseManager 需要的全部后端相关行为。"""

    #: 方言名称，'sqlite' | 'mysql'
    name: str = ""

    # ---- 连接与事务 -------------------------------------------------

    @abstractmethod
    def connect(self):
        """返回一个已配置好的 DBAPI 连接。

        MySQL 方言返回的是「翻译连接」包装器：其 cursor 会在 execute /
        executemany 前把 SQLite 风格 SQL 翻译为 MySQL 语法，从而让
        DatabaseManager 内部调用与散落各处的 ``conn.cursor().execute`` 同时受益。
        """

    @abstractmethod
    def setup(self) -> None:
        """一次性的数据库级配置（SQLite: PRAGMA；MySQL: 确保库存在/字符集）。"""

    @abstractmethod
    def begin(self, conn) -> None:
        """在给定连接上开启一个事务。"""

    def commit(self, conn) -> None:
        conn.commit()

    def rollback(self, conn) -> None:
        conn.rollback()

    # ---- 结构内省 ---------------------------------------------------

    @abstractmethod
    def table_exists(self, executor, table_name: str) -> bool:
        ...

    @abstractmethod
    def get_table_columns(self, executor, table_name: str) -> List[Dict[str, Any]]:
        """返回归一化列信息：{'cid','name','type','notnull','default_value','pk'}。"""

    @abstractmethod
    def get_all_tables(self, executor) -> List[str]:
        ...

    # ---- DDL --------------------------------------------------------

    @abstractmethod
    def create_table(self, executor, table_name: str,
                     columns: List[Dict[str, Any]],
                     indexes: Optional[List[Dict[str, Any]]] = None) -> bool:
        ...

    @abstractmethod
    def add_column(self, executor, table_name: str, column_def: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def drop_column(self, executor, table_name: str, column_name: str) -> bool:
        ...

    def drop_table(self, executor, table_name: str) -> bool:
        try:
            executor.execute_update(f"DROP TABLE IF EXISTS [{table_name}]")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"删除表 {table_name} 失败: {e}")
            return False

    # ---- JSON 数组展开（combined_items / images_json 等） ----------

    @abstractmethod
    def json_array_each(self, json_col_expr: str, alias: str) -> str:
        """返回 FROM 子句片段：把 JSON 数组展开为多行，每行含 ``.value`` 列。

        SQLite: ``json_each(<expr>) <alias>``；
        MySQL : ``JSON_TABLE(<expr>, '$[*]' COLUMNS(value JSON PATH '$')) <alias>``。
        """

    @abstractmethod
    def json_array_each_text(self, json_col_expr: str, alias: str) -> str:
        """同 ``json_array_each``，但每行 ``.value`` 为「文本」（用于标量字符串数组，
        如 images_json）。MySQL 下按 VARCHAR 取值以避免 JSON 引号。"""

    @abstractmethod
    def json_extract_int(self, value_expr: str, key: str) -> str:
        """从 JSON 对象元素中取整数字段的表达式。"""

    @abstractmethod
    def greatest(self, *exprs: str) -> str:
        """标量「取最大值」表达式。SQLite: ``MAX(a, b)``；MySQL: ``GREATEST(a, b)``
        （MySQL 的 ``MAX`` 是聚合函数，不能用于逐行取大）。"""

    @abstractmethod
    def table_source(self, table_expr: str, alias: str, materialize: bool = False) -> str:
        """FROM 子句里的表来源。``materialize=True`` 时，MySQL 包成派生表
        ``(SELECT * FROM t) alias`` 以规避「UPDATE 目标表不能在子查询 FROM 中再引用」
        （错误 1093）；SQLite 无此限制，恒等返回 ``t alias``。"""
