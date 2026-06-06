# -*- coding: utf-8 -*-
"""系统启动就绪标志。

main.py 在 startup 事件全部执行完毕后调用 mark_ready()，
健康检查（/api/health 与 /mercariV2/health）据此判断是否真正就绪，
避免在启动过程中（数据库初始化、代理拉起、后台任务调度未完成）就被判定为就绪。
"""

from __future__ import annotations

_ready = False


def mark_ready() -> None:
    global _ready
    _ready = True


def is_ready() -> bool:
    return _ready
