# -*- coding: utf-8 -*-
"""SQLite → MySQL 数据搬迁工具（一次性）。

用法（在 backend 目录下）：

    # 目标 MySQL 连接信息通过环境变量提供
    set MYSQL_HOST=127.0.0.1
    set MYSQL_PORT=3306
    set MYSQL_USER=root
    set MYSQL_PASSWORD=yourpass
    set MYSQL_DATABASE=mercari
    python -m tools.sqlite_to_mysql              # 从 backend/mercariDB.db 搬迁
    python -m tools.sqlite_to_mysql --src D:/path/mercariDB.db --yes

流程：
  1. 以 DB_BACKEND=mysql 运行应用自身的 init_database()，按模型在 MySQL 建出全部表
     （历史 SQLite 迁移已被 sqlite-only 守卫跳过）。
  2. 逐表把 SQLite 数据分批写入 MySQL（仅拷贝两侧都存在的列）。
  3. 逐表比对行数，输出校验结果。

不改动源 SQLite 库；可安全重复运行（目标表会先 TRUNCATE 再导入）。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

BATCH = 500


def _src_path(explicit: str | None) -> str:
    if explicit:
        return explicit
    root = os.environ.get("MERCARI_BACKEND_ROOT") or os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    return os.path.join(root, "mercariDB.db")


def _sqlite_columns(scur, table: str) -> list[str]:
    scur.execute(f"PRAGMA table_info([{table}])")
    return [r[1] for r in scur.fetchall()]


def _sqlite_tables(scur) -> list[str]:
    scur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in scur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="源 SQLite 文件路径（默认 backend/mercariDB.db）")
    ap.add_argument("--yes", action="store_true", help="跳过确认直接执行")
    args = ap.parse_args()

    src = _src_path(args.src)
    if not os.path.exists(src):
        print(f"[错误] 源 SQLite 不存在: {src}")
        return 2

    os.environ["DB_BACKEND"] = "mysql"
    # 让应用能 import（tools 在 backend 下，backend 需在 sys.path）
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.db_manage.db_manager import init_database, get_db_manager  # noqa: E402

    mgr = get_db_manager()
    db = mgr.db  # DatabaseManager（mysql 后端）
    print(f"源:   {src}")
    print(f"目标: MySQL {db.dialect.host}:{db.dialect.port}/{db.dialect.database}")
    if not args.yes:
        if input("确认开始搬迁？(yes/no) ").strip().lower() not in ("y", "yes"):
            print("已取消")
            return 1

    print("\n[1/3] 在 MySQL 建立表结构 ...")
    if not init_database():
        print("[错误] MySQL 建表失败，终止")
        return 3

    from src.db_manage.migrate import _sanitize_datetime_value  # noqa: E402

    sconn = sqlite3.connect(src)
    scur = sconn.cursor()
    src_tables = set(_sqlite_tables(scur))
    model_tables = [m.get_table_name() for m in mgr.models]
    model_by_table = {m.get_table_name(): m for m in mgr.models}

    print("\n[2/3] 逐表搬迁数据 ...")
    # 关外键校验，避免导入顺序问题
    db.execute_update("SET FOREIGN_KEY_CHECKS=0")
    summary = []
    for table in model_tables:
        if table not in src_tables:
            summary.append((table, 0, 0, "源无此表，跳过"))
            continue
        my_cols = {c["name"] for c in db.get_table_columns(table)}
        cols = [c for c in _sqlite_columns(scur, table) if c in my_cols]
        if not cols:
            summary.append((table, 0, 0, "无公共列，跳过"))
            continue

        db.execute_update(f"TRUNCATE TABLE [{table}]")
        col_sql = ", ".join(f"[{c}]" for c in cols)
        ph = ", ".join("?" * len(cols))
        insert_sql = f"INSERT INTO [{table}] ({col_sql}) VALUES ({ph})"

        # DATETIME 列下标：净化非法时间值（如残留的 'CURRENT_TIMESTAMP'）
        _fdefs = model_by_table[table].get_fields()
        dt_idx = [
            i for i, c in enumerate(cols)
            if 'DATE' in str(_fdefs.get(c, {}).get('type', '')).upper()
            or 'TIME' in str(_fdefs.get(c, {}).get('type', '')).upper()
        ]

        scur.execute(f"SELECT {col_sql} FROM [{table}]")
        moved = 0
        while True:
            batch = scur.fetchmany(BATCH)
            if not batch:
                break
            if dt_idx:
                params = []
                for r in batch:
                    row = list(r)
                    for j in dt_idx:
                        row[j] = _sanitize_datetime_value(row[j])
                    params.append(tuple(row))
            else:
                params = [tuple(r) for r in batch]
            db.execute_many(insert_sql, params)
            moved += len(batch)

        src_count = scur.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        dst_count = db.execute_query(f"SELECT COUNT(*) FROM [{table}]")[0][0]
        ok = "OK" if src_count == dst_count else "!! 行数不一致"
        summary.append((table, src_count, dst_count, ok))
        print(f"  {table:<34} 源={src_count:<7} 目标={dst_count:<7} {ok}")

    db.execute_update("SET FOREIGN_KEY_CHECKS=1")
    sconn.close()

    print("\n[3/3] 校验汇总：")
    bad = [s for s in summary if s[3].startswith("!!")]
    for t, sc, dc, st in summary:
        print(f"  {t:<34} {sc:>7} -> {dc:>7}  {st}")
    if bad:
        print(f"\n[警告] {len(bad)} 张表行数不一致，请检查。")
        return 4
    print("\n[完成] 全部表行数一致，搬迁成功。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
