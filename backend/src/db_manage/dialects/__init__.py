# -*- coding: utf-8 -*-
"""数据库方言工厂。

通过环境变量 ``DB_BACKEND`` 选择后端：
  · ``sqlite``（默认）—— 现有行为，零改动。
  · ``mysql``          —— MySQL 8.0+（PyMySQL）。

选择 ``mysql`` 时可用的环境变量：
  MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE / MYSQL_POOL_SIZE
"""

from __future__ import annotations

from .base import Dialect


def get_dialect(sqlite_db_path: str) -> Dialect:
    # 后端选择来自 bootstrap 配置存储（system.db），其次环境变量，最后默认 sqlite。
    from ..db_settings import get_active_backend, get_mysql_config
    if get_active_backend() == "mysql":
        from .mysql import MysqlDialect
        return MysqlDialect(get_mysql_config())
    from .sqlite import SqliteDialect
    return SqliteDialect(sqlite_db_path)


__all__ = ["Dialect", "get_dialect"]
