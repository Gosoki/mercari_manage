# -*- coding: utf-8 -*-
"""
MITM 自动化：按账号打开主 profile ``meilu_{id}`` 的有头 Edge 浏览器,
经 MITM 代理捕获煤炉 API 响应。

设计要点：
  - 直接使用主 profile,登录态由 Edge 持久化 cookie 自动维护,无需 cookie seed
    与首页 prewarm。
  - 同账号通过 ``run_meilu_serial_async`` 串行执行,无并发问题;
    浏览器自动关闭由队列(``account_serial_queue.py``)负责:队列归 0 后
    经 ``WEB_DRIVE_QUEUE_IDLE_CLOSE_SEC`` 秒延迟自动关闭。
  - 若同账号已存在「非 MITM 代理」的主浏览器(用户从 /meilu-accounts 打开的),
    首次进入会强制关闭并以 MITM 代理重新启动。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, Optional, Tuple

from ...ssl_mitm_proxy.runner import default_mitm_proxy_url, start_mitm_proxy
from .manager import (
    EdgeWebDriveManager,
    automation_headless_enabled,
    get_web_drive_manager,
)
from .paths import meilu_account_key

log = logging.getLogger(__name__)

_MITM_PAGE_RELOAD_INTERVAL_SEC = 20.0

# 煤炉登录页 URL 模式：cookies 过期时所有目标页都会 302 到这里
_MERCARI_LOGIN_URL_RE = re.compile(
    r"^https?://login\.jp\.mercari\.com/",
    re.IGNORECASE,
)


class MercariLoginRequiredError(RuntimeError):
    """打开账号浏览器后跳到 ``login.jp.mercari.com`` 登录页：账号 cookie 已失效。

    抛出前已将 ``meilu_accounts.status`` 置为 ``'disabled'``，并强制关闭该账号
    的 MITM 浏览器。前端可在「煤炉账号」页打开浏览器手动重新登录后再启用账号。
    """

    def __init__(
        self,
        *,
        account_id: int,
        account_name: str = "",
        login_url: str = "",
    ) -> None:
        self.account_id = int(account_id)
        self.account_name = (account_name or "").strip()
        self.login_url = (login_url or "").strip()
        label = self.account_name or f"#{self.account_id}"
        super().__init__(
            f"煤炉账号「{label}」登录态已失效（浏览器被重定向到登录页），"
            f"已将账号状态置为「停用」。请到「煤炉账号」页面打开浏览器手动登录后再启用。"
        )


def _is_mercari_login_url(url: Optional[str]) -> bool:
    if not url:
        return False
    return bool(_MERCARI_LOGIN_URL_RE.match(str(url).strip()))


async def _detect_login_redirect_and_disable(
    mgr: EdgeWebDriveManager,
    account_id: int,
    main_key: str,
    *,
    max_wait_ms: int = 2000,
) -> None:
    """打开浏览器后检测是否被重定向到煤炉登录页。

    - 在 ``max_wait_ms`` 内轮询当前活动标签 URL：
        - 命中登录页 → 立刻关闭浏览器、将账号 ``status`` 置 ``'disabled'``、
          抛 ``MercariLoginRequiredError``
        - 命中非空且非登录的 URL → 视为正常加载,提前返回
    - 全程命中空白 / about:blank → 视为加载未完成,达到超时后视作正常返回(不
      误判)
    """
    deadline = time.monotonic() + max_wait_ms / 1000
    detected_login_url = ""
    while time.monotonic() < deadline:
        cur_url = ""
        try:
            page = await mgr.active_tab_page(main_key)
            cur_url = (page.url or "").strip()
        except Exception:
            cur_url = ""
        if _is_mercari_login_url(cur_url):
            detected_login_url = cur_url
            break
        if cur_url and "about:blank" not in cur_url.lower():
            # 已有真实目标页 URL（非登录）→ 提前认为正常返回
            return
        await asyncio.sleep(0.15)

    if not detected_login_url:
        return

    # ── 命中登录页：停账号 + 关浏览器 + 抛错 ───────────────────────── #
    account_name = ""
    try:
        from ...db_manage.models.meilu_account import MeiluAccountModel

        acc = MeiluAccountModel.find_by_id(id=int(account_id))
        if acc is not None:
            account_name = str(getattr(acc, "account_name", "") or "").strip()
            if str(getattr(acc, "status", "") or "").strip() != "disabled":
                acc.status = "disabled"
                try:
                    acc.save()
                    log.warning(
                        "[mitm] 浏览器被重定向到登录页，已停用账号 account_id=%d name=%s url=%s",
                        account_id,
                        account_name,
                        detected_login_url,
                    )
                except Exception as exc:
                    log.warning(
                        "[mitm] 标记账号停用失败 account_id=%d: %s",
                        account_id,
                        exc,
                    )
    except Exception as exc:
        log.warning(
            "[mitm] 读取账号失败 account_id=%d: %s", account_id, exc
        )

    # 关闭被登录页占用的浏览器，避免后续操作再次进入相同失效会话
    try:
        await mgr.close_session(main_key, force=True)
    except Exception as exc:
        log.warning(
            "[mitm] 登录态失效关浏览器失败 account_id=%d: %s",
            account_id,
            exc,
        )

    raise MercariLoginRequiredError(
        account_id=int(account_id),
        account_name=account_name,
        login_url=detected_login_url,
    )


def _default_minimized() -> bool:
    """MITM 自动化浏览器是否默认在后台(最小化)运行。

    通过 ``WEB_DRIVE_MITM_MINIMIZED`` 环境变量覆盖,接受 0/false/no/off 关闭;
    其余值(含未设置)视为开启,即默认窗口最小化、不抢占前台。
    """
    raw = (os.environ.get("WEB_DRIVE_MITM_MINIMIZED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


async def _is_context_alive(mgr: EdgeWebDriveManager, key: str) -> bool:
    """检查指定 key 的 context 在 manager 内是否仍存活(用户未手动关窗)。"""
    s = mgr._prepare_async()
    async with s.lock:  # type: ignore[union-attr]
        ctx = s.contexts.get(key)
        return ctx is not None and mgr._is_context_alive(ctx)


async def _launch_with_mitm(
    *,
    mgr: EdgeWebDriveManager,
    account_id: int,
    main_key: str,
    target_url: str,
    minimized: bool = True,
    headless: bool = False,
) -> None:
    """启动账号主 profile Edge,直接进入目标页(经 MITM 代理)。

    若同 profile 已有进程(无 MITM 代理),强制关闭后重启。
    ``headless=True`` 时启动无头浏览器(``minimized`` 自动失效);
    ``headless=False`` 且 ``minimized=True`` 时浏览器窗口最小化到任务栏(后台运行,不抢前台)。
    """
    r = start_mitm_proxy()
    if r.get("error"):
        raise RuntimeError(f"MITM 代理不可用: {r['error']}")

    if mgr.is_interactive_session_running(main_key):
        log.info(
            "[mitm] account_id=%d 主浏览器已在运行(无 MITM 代理),强制关闭后以 MITM 重新打开",
            account_id,
        )
        try:
            await mgr.close_session(main_key, force=True)
        except Exception as exc:
            log.warning("[mitm] 关闭主浏览器失败(继续尝试启动): %s", exc)

    proxy = default_mitm_proxy_url()
    target = (target_url or "").strip() or "https://jp.mercari.com/"

    await mgr.open_session(
        main_key,
        headless=headless,
        start_url=target,
        proxy_server=proxy,
        interactive=not headless,
        restore_tabs=False,
        start_minimized=bool(minimized),
    )

    if not await _is_context_alive(mgr, main_key):
        raise RuntimeError(
            f"主 profile MITM 浏览器启动失败: {main_key}。请检查 Edge / Playwright 状态后重试。"
        )


async def shutdown_mitm_leases() -> None:
    """旧版兼容入口:新版无内部租借状态需要清理(由队列负责),保留为 no-op。"""
    return None


@asynccontextmanager
async def mitm_automation_browser(
    account_id: int,
    *,
    start_url: str,
    minimized: Optional[bool] = None,
) -> AsyncIterator[Tuple[EdgeWebDriveManager, str]]:
    """
    上下文管理器:进入时确保账号主 profile 浏览器已开(走 MITM 代理),并导航到目标页。

    yield ``(mgr, main_key)``;退出时**不关闭**浏览器——关闭由队列层
    (``account_serial_queue._delayed_close_browser``)按 ``WEB_DRIVE_QUEUE_IDLE_CLOSE_SEC``
    延迟自动处理。

    ``minimized``: 启动时是否最小化(后台运行)。``None`` = 读环境变量
    ``WEB_DRIVE_MITM_MINIMIZED``(默认 ``"1"`` = 最小化)。已有浏览器复用时仅
    刷新标签页,不会重新决定窗口状态。
    """
    aid = int(account_id)
    main_key = meilu_account_key(aid)
    mgr = get_web_drive_manager()
    target_url = (start_url or "").strip()
    use_minimized = _default_minimized() if minimized is None else bool(minimized)
    use_headless = automation_headless_enabled()

    if await _is_context_alive(mgr, main_key):
        # 复用:仅刷新当前标签页到目标 URL
        if target_url:
            try:
                await mgr.reload_active_tab(main_key, target_url)
                log.debug("[mitm] 复用主浏览器 account_id=%d → %s", aid, target_url)
            except Exception as exc:
                log.warning(
                    "[mitm] 复用 reload 失败,强制重启浏览器 account_id=%d: %s",
                    aid,
                    exc,
                )
                try:
                    await mgr.close_session(main_key, force=True)
                except Exception:
                    pass
                await _launch_with_mitm(
                    mgr=mgr,
                    account_id=aid,
                    main_key=main_key,
                    target_url=target_url,
                    minimized=use_minimized,
                    headless=use_headless,
                )
    else:
        await _launch_with_mitm(
            mgr=mgr,
            account_id=aid,
            main_key=main_key,
            target_url=target_url,
            minimized=use_minimized,
            headless=use_headless,
        )

    # ── 检测登录态失效（重定向到 login.jp.mercari.com）── #
    # 命中则关浏览器 + 将 meilu_accounts.status 置为 'disabled' + 抛错；
    # 失败/正常加载则提前返回，不影响后续 MITM 截获。
    await _detect_login_redirect_and_disable(mgr, aid, main_key)

    yield mgr, main_key


async def wait_mitm_capture(
    *,
    mgr: EdgeWebDriveManager,
    auto_key: str,
    start_url: str,
    read_response: Callable[[], Optional[Dict[str, Any]]],
    since_ms: int,
    wait_seconds: int,
    error_detail: str,
    reload_interval_sec: float = _MITM_PAGE_RELOAD_INTERVAL_SEC,
) -> Dict[str, Any]:
    """
    轮询 MITM 落盘文件;超时前按间隔刷新当前标签页以再次触发目标 API。

    形参名 ``auto_key`` 系历史命名,实际传任意会话 key
    (新版传入 ``meilu_account_key(aid)`` 主 profile key)。
    """
    deadline = time.monotonic() + wait_seconds
    next_reload = time.monotonic() + reload_interval_sec
    while time.monotonic() < deadline:
        data = read_response()
        if data and int(data.get("ts") or 0) >= since_ms:
            return data
        if time.monotonic() >= next_reload:
            next_reload += reload_interval_sec
            try:
                await mgr.reload_active_tab(auto_key, start_url)
            except Exception as exc:
                log.debug("MITM 等待中刷新标签页失败: %s", exc)
        await asyncio.sleep(0.35)
    raise RuntimeError(
        f"{wait_seconds}s 内未截获目标 API 响应({error_detail})。"
        "请确认 MITM 已启动;并先在账号管理页对该账号完成 Mercari 登录(主 profile 会持久化登录态)。"
    )
