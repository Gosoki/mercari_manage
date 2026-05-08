# -*- coding: utf-8 -*-
"""
Mercari 出品自动化：打开 https://jp.mercari.com/sell/create 并填写表单。

执行步骤：
  1. 用 MITM 代理启动（或复用）指定账号的 Edge 持久化会话
  2. 导航到出品页
  3. 点击「写真を追加」按钮 → 文件选择器上传正/背面图
  4. 填写商品名称
  5. 填写商品说明
"""
from __future__ import annotations

import logging
import os
import tempfile
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

# ───────────────────────── Mercari 出品页 XPath ──────────────────────────── #

SELL_CREATE_URL = "https://jp.mercari.com/sell/create"

# 写真ブロック内「写真を追加」按钮（含 span 子节点）
PHOTO_ADD_BUTTON_XPATH = (
    '//*[@id="main"]/form/section[1]/div/div[6]/div[2]/button'
)

# 需要确保处于 false（关闭）状态的 Switch 开关 input
# aria-checked="true" 时点击一次使其恢复 false
SWITCH_INPUT_XPATH = (
    '//*[@id="main"]/form/section[1]/div/div[2]/label/div[2]/div/div/div/input'
)

# 商品名称输入框
NAME_INPUT_XPATH = (
    '//*[@id="main"]/form/section[2]/div[2]/div/div[1]/input'
)

# 商品说明 textarea
DESCRIPTION_TEXTAREA_XPATH = (
    '//*[@id="main"]/form/div[1]/div/label/textarea[1]'
)

# ──────────────────────────── 工具函数 ──────────────────────────────────── #

def _backend_imges_root() -> str:
    """返回 backend/imges 目录的绝对路径。"""
    here = os.path.dirname(os.path.abspath(__file__))
    # post_to_macket.py → web_operate → web_drive → src → backend
    backend = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(backend, "imges")


def _resolve_image_to_local(url_or_path: str) -> Optional[str]:
    """
    将图片 URL 或路径解析为本地绝对路径（供 Playwright set_input_files 使用）。

    - /imges/xxx.jpg  → backend/imges/xxx.jpg
    - http(s)://...   → 下载到系统临时目录
    - 本地绝对路径    → 直接返回
    返回 None 表示无法处理。
    """
    s = (url_or_path or "").strip()
    if not s:
        return None

    # 本地相对路径 /imges/...
    if s.startswith("/imges/"):
        filename = s.split("/imges/", 1)[1].strip("/")
        if not filename:
            return None
        abs_path = os.path.join(_backend_imges_root(), filename)
        return abs_path if os.path.isfile(abs_path) else None

    # 本地绝对路径
    if os.path.isabs(s):
        return s if os.path.isfile(s) else None

    # 外部 HTTP(S) URL → 下载到临时文件
    if s.startswith("http://") or s.startswith("https://"):
        ext = ".jpg"
        for candidate in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            if s.lower().split("?")[0].endswith(candidate):
                ext = candidate
                break
        try:
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tf.close()
            urllib.request.urlretrieve(s, tf.name)
            return tf.name
        except Exception as exc:
            log.warning("下载图片失败 %s: %s", s, exc)
            return None

    return None


# ──────────────────────────── 主函数 ────────────────────────────────────── #

async def post_to_market(
    manager: Any,
    account_key: str,
    *,
    name: str = "",
    description: str = "",
    image_urls: Sequence[str] = (),
    proxy_server: Optional[str] = None,
    page_load_timeout_ms: int = 30_000,
    element_timeout_ms: int = 20_000,
) -> Dict[str, Any]:
    """
    自动填写 Mercari 出品表单（第一步：图片上传 + 商品名 + 商品说明）。

    参数：
        manager         EdgeWebDriveManager 实例
        account_key     账号标识（如 meilu_1）
        name            商品名称
        description     商品说明（已含管理番号行）
        image_urls      图片路径列表：/imges/xxx.jpg 或 http(s):// URL
        proxy_server    MITM 代理地址（不填则取 runner.default_mitm_proxy_url）
        page_load_timeout_ms  页面加载超时
        element_timeout_ms    元素等待超时
    """
    from ..manager import EdgeWebDriveManager  # 避免循环引用

    if not isinstance(manager, EdgeWebDriveManager):
        raise TypeError("manager 须为 EdgeWebDriveManager 实例")

    # ── 1. 解析代理地址 ──────────────────────────────────────────────────── #
    ps = (proxy_server or "").strip()
    if not ps:
        try:
            from ...ssl_mitm_proxy.runner import default_mitm_proxy_url
            ps = default_mitm_proxy_url()
        except Exception:
            ps = "http://127.0.0.1:8890"

    # ── 2. 解析图片为本地路径 ────────────────────────────────────────────── #
    local_images: List[str] = []
    for u in image_urls:
        p = _resolve_image_to_local(u)
        if p:
            local_images.append(p)
        else:
            log.warning("无法解析图片路径，跳过: %s", u)

    # ── 3. 确保会话已启动，并导航到出品页 ──────────────────────────────── #
    await manager.open_session(
        account_key,
        headless=False,
        start_url=SELL_CREATE_URL,
        proxy_server=ps,
    )

    async with manager._lock:
        ctx = manager._contexts.get(account_key)
        if ctx is None or not manager._is_context_alive(ctx):
            raise RuntimeError(f"会话启动失败: {account_key}")
        page = ctx.pages[-1] if ctx.pages else await ctx.new_page()

    # ── 4. 等待页面可交互 ────────────────────────────────────────────────── #
    try:
        await page.wait_for_load_state("networkidle", timeout=page_load_timeout_ms)
    except Exception:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=page_load_timeout_ms)
        except Exception:
            pass

    result: Dict[str, Any] = {
        "account_key": account_key,
        "url": page.url,
        "switch_checked": None,
        "switch_clicked": False,
        "images_uploaded": 0,
        "name_filled": False,
        "description_filled": False,
    }

    # ── 5. 确保 Switch 开关处于 false（关闭）状态 ────────────────────────── #
    try:
        switch_loc = page.locator(f"xpath={SWITCH_INPUT_XPATH}")
        await switch_loc.first.wait_for(state="attached", timeout=element_timeout_ms)

        # 读取 aria-checked 属性（值为字符串 "true" / "false"）
        aria_checked = await switch_loc.first.get_attribute("aria-checked")
        result["switch_checked"] = aria_checked
        log.info("[post_to_market] Switch aria-checked = %s", aria_checked)

        if (aria_checked or "").lower() == "true":
            # 点击父级 label 触发切换（input[type=checkbox][disabled] 不可直接 click）
            label_loc = page.locator(
                'xpath=//*[@id="main"]/form/section[1]/div/div[2]/label'
            )
            await label_loc.first.click(timeout=element_timeout_ms)
            result["switch_clicked"] = True
            log.info("[post_to_market] Switch 已由 true 切换为 false")

            # 等待 aria-checked 变为 false
            try:
                await page.wait_for_function(
                    """(xpath) => {
                        const r = document.evaluate(
                            xpath, document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null
                        );
                        const el = r.singleNodeValue;
                        return el && el.getAttribute('aria-checked') !== 'true';
                    }""",
                    SWITCH_INPUT_XPATH,
                    timeout=5_000,
                )
            except Exception:
                pass
    except Exception as exc:
        log.warning("[post_to_market] 检查/切换 Switch 失败: %s", exc)
        result["switch_error"] = str(exc)

    # ── 6. 图片上传 ──────────────────────────────────────────────────────── #
    if local_images:
        try:
            btn_locator = page.locator(f"xpath={PHOTO_ADD_BUTTON_XPATH}")
            await btn_locator.first.wait_for(state="visible", timeout=element_timeout_ms)

            # 每次点击只能选一次文件；Mercari 支持多选
            async with page.expect_file_chooser(timeout=element_timeout_ms) as fc_info:
                await btn_locator.first.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(local_images)

            result["images_uploaded"] = len(local_images)
            log.info("[post_to_market] 图片已上传：%d 张", len(local_images))

            # 等待上传缩略图出现（最多 10 秒）
            try:
                await page.wait_for_selector(
                    "img[alt*='写真'], img[alt*='photo'], section img",
                    timeout=10_000,
                )
            except Exception:
                pass

            # 点击「完了」按钮关闭图像选择弹窗
            try:
                close_btn = page.locator(
                    'xpath=//*[@id="modal"]/div[3]/div/button'
                )
                await close_btn.first.wait_for(state="visible", timeout=element_timeout_ms)
                await close_btn.first.click()
                log.info("[post_to_market] 图像选择弹窗已关闭")
                # 等待弹窗消失
                try:
                    await close_btn.first.wait_for(state="hidden", timeout=5_000)
                except Exception:
                    pass
            except Exception as exc:
                log.warning("[post_to_market] 关闭图像选择弹窗失败（可能已自动关闭）: %s", exc)
                result["modal_close_warning"] = str(exc)
        except Exception as exc:
            log.error("[post_to_market] 图片上传失败: %s", exc)
            result["images_error"] = str(exc)

    # ── 7. 填写商品名称 ──────────────────────────────────────────────────── #
    name_str = (name or "").strip()
    if name_str:
        try:
            name_loc = page.locator(
                f"xpath={NAME_INPUT_XPATH}"
            ).or_(page.locator('input[name="name"]')).or_(
                page.locator('[data-testid="input-name"] input')
            )
            await name_loc.first.wait_for(state="visible", timeout=element_timeout_ms)
            await name_loc.first.scroll_into_view_if_needed()
            await name_loc.first.click()
            await page.wait_for_timeout(100)

            # React 受控 input：原生 setter + 完整事件链
            filled = await page.evaluate(
                """([xpath, value]) => {
                    let el = null;
                    try {
                        const r = document.evaluate(
                            xpath, document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null
                        );
                        el = r.singleNodeValue;
                    } catch(e) {}
                    if (!el) el = document.querySelector('input[name="name"]');
                    if (!el) el = document.querySelector('[data-testid="input-name"] input');
                    if (!el) return false;

                    el.focus();
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(el, value);
                    el.dispatchEvent(new Event('focus',  { bubbles: true }));
                    el.dispatchEvent(new Event('input',  { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('keyup',  { bubbles: true }));
                    el.dispatchEvent(new Event('blur',   { bubbles: true }));
                    return true;
                }""",
                [NAME_INPUT_XPATH, name_str],
            )

            if not filled:
                log.warning("[post_to_market] 方法A未定位到名称框，改用键盘输入")
                await name_loc.first.focus()
                await page.keyboard.press("Control+a")
                await page.keyboard.type(name_str, delay=0)

            result["name_filled"] = True
            log.info("[post_to_market] 商品名称已填写")
        except Exception as exc:
            log.error("[post_to_market] 填写商品名称失败: %s", exc)
            result["name_error"] = str(exc)

    # ── 8. 填写商品说明 ──────────────────────────────────────────────────── #
    desc_str = (description or "").strip()
    if desc_str:
        try:
            # 优先通过 XPath 定位；同时提供 name/data-testid 兜底选择器
            desc_loc = page.locator(
                f"xpath={DESCRIPTION_TEXTAREA_XPATH}"
            ).or_(page.locator('textarea[name="description"]')).or_(
                page.locator('[data-testid="input-description"] textarea')
            )
            await desc_loc.first.wait_for(state="visible", timeout=element_timeout_ms)

            # 滚动到视图内，确保元素可交互
            await desc_loc.first.scroll_into_view_if_needed()

            # 点击 → focus，等 React 完成 focus 处理
            await desc_loc.first.click()
            await page.wait_for_timeout(150)

            # 方法 A：React 原生 setter + 完整事件链（focus→input→change→blur）
            filled = await page.evaluate(
                """([xpath, value]) => {
                    // 多策略定位元素
                    let el = null;
                    try {
                        const r = document.evaluate(
                            xpath, document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null
                        );
                        el = r.singleNodeValue;
                    } catch(e) {}
                    if (!el) el = document.querySelector('textarea[name="description"]');
                    if (!el) el = document.querySelector('[data-testid="input-description"] textarea');
                    if (!el) return false;

                    el.focus();
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    setter.call(el, value);
                    el.dispatchEvent(new Event('focus',  { bubbles: true }));
                    el.dispatchEvent(new Event('input',  { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('keyup',  { bubbles: true }));
                    el.dispatchEvent(new Event('blur',   { bubbles: true }));
                    return true;
                }""",
                [DESCRIPTION_TEXTAREA_XPATH, desc_str],
            )

            if not filled:
                # 方法 B 兜底：全选后键盘逐字输入（慢但最可靠）
                log.warning("[post_to_market] 方法A未定位到描述框，改用键盘输入")
                await desc_loc.first.focus()
                await page.keyboard.press("Control+a")
                await page.keyboard.type(desc_str, delay=0)

            result["description_filled"] = True
            log.info("[post_to_market] 商品说明已填写")
        except Exception as exc:
            log.error("[post_to_market] 填写商品说明失败: %s", exc)
            result["description_error"] = str(exc)

    return result
