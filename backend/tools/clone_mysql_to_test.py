# -*- coding: utf-8 -*-
"""一次性：把当前 MySQL 生产库（mercari）全库克隆到测试库（默认 freemarket_test）。

复用 ``src/db_manage/migrate.migrate``：按当前模型在目标库建表并逐表拷贝数据。
**只读源库（mercari）、只写目标库（freemarket_test）**，绝不改动源库。

用法（在 backend 目录下）：
    python -m tools.clone_mysql_to_test
    python -m tools.clone_mysql_to_test --target freemarket_test --yes

说明：
- 源库 = 当前生效后端（见 backend/system.db 的 db_backend/mysql_database，须为 mysql）。
- 目标库若不存在且账号有建库权限则自动创建（MysqlDialect.setup）；否则请管理员先建库。
- 目标表会先删表重建再整表回填；可安全重复运行。
- 目标库名与源库名相同时直接拒绝，防止误写生产。
- 本脚本运行时的 schema 以「当前模型定义」为准（platform 列在 Step 2 加入模型后，
  由应用连上测试库时的 ensure_table_exists 自动补列，无需在此处理）。
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="freemarket_test", help="目标测试库名（默认 freemarket_test）")
    ap.add_argument("--yes", action="store_true", help="跳过确认直接执行")
    args = ap.parse_args()

    # 让应用可 import（tools 在 backend 下，backend 需在 sys.path）
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.db_manage.db_settings import get_active_backend, get_mysql_config
    from src.db_manage.db_manager import get_db_manager
    from src.db_manage.dialects.mysql import MysqlDialect
    from src.db_manage.migrate import migrate

    if get_active_backend() != "mysql":
        print("[错误] 当前生效后端不是 mysql；源库必须是 MySQL(mercari)。终止。")
        return 2

    cfg = get_mysql_config()
    src_name = (cfg.get("database") or "").strip()
    target_name = (args.target or "").strip()
    if not target_name:
        print("[错误] 目标库名为空")
        return 2
    if target_name == src_name:
        print(f"[错误] 目标库 `{target_name}` 与源库相同，拒绝执行（防误写生产）。")
        return 2

    mgr = get_db_manager()  # 源 = 当前后端（mercari），migrate 只读它
    target_cfg = {**cfg, "database": target_name}
    target_dialect = MysqlDialect(target_cfg)

    print(f"源  : MySQL {cfg['host']}:{cfg['port']}/{src_name}   (只读)")
    print(f"目标: MySQL {cfg['host']}:{cfg['port']}/{target_name}   (只写；先删表重建再整表回填)")
    print(f"表数: {len(mgr.models)}")
    if not args.yes:
        if input("确认开始克隆？(yes/no) ").strip().lower() not in ("y", "yes"):
            print("已取消")
            return 1

    print("\n克隆中 ...")
    result = migrate(mgr.db, target_dialect, mgr.models)

    print("\n逐表校验：")
    for s in result["tables"]:
        print(f"  {s['table']:<34} 源={s['src']:>7} -> 目标={s['dst']:>7}   {s['status']}")

    if result["ok"]:
        print("\n[完成] 全部表行数一致，克隆成功。")
        return 0
    print(f"\n[警告] {len(result['mismatch'])} 张表行数不一致，请检查。")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
