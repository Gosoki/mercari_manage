# -*- coding: utf-8 -*-
"""
代办事项 →「处理」按钮：打开 https://jp.mercari.com/transaction/<item_id>，
通过 Playwright page.evaluate 提取交易页字段（商品名、发送元、当前发送方式、
两个发货按钮的可用性、消息流、左侧 sidebar 的费用/时间/配送等）。

浏览器在抓取后 **保持打开**，方便用户在原生页面上手动操作；下一次「处理」
按钮调用会先关掉旧的 ``__auto`` 会话再开新的（``ensure_session_for_mitm`` 自带）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from ...db_manage.models.todo_item import TodoItemModel
from ...ssl_mitm_proxy.runner import default_mitm_proxy_url, start_mitm_proxy
from ...web_drive.core.manager import get_web_drive_manager
from ...web_drive.core.paths import (
    meilu_automation_key,
    seed_automation_profile_from_account,
)

log = logging.getLogger(__name__)


_EXTRACT_JS = r"""
() => {
  const result = {
    product_name: null,
    sender_address: null,
    current_shipping_status: null,
    has_size_location_btn: false,
    has_change_method_btn: false,
    messages: [],
    buyer_name: null,
    buyer_verified: false,
    price: null,
    fee: null,
    profit: null,
    shipping_fee_label: null,
    purchase_time: null,
    delivery_method: null,
    debug: { url: location.href }
  };

  const xpath = (expr) => {
    try {
      return document.evaluate(expr, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    } catch (e) { return null; }
  };
  const tx = (el) => (el && el.innerText ? el.innerText.trim() : '');
  const parseYen = (s) => {
    if (s == null) return null;
    const m = String(s).match(/[\d,]+/);
    if (!m) return null;
    const n = Number(m[0].replace(/,/g, ''));
    return Number.isFinite(n) ? n : null;
  };

  // 商品名（input 的 value）
  const nameInput = xpath('/html/body/div[2]/div[2]/main/div/div[2]/div[2]/form/div[4]/div/label/div/input');
  if (nameInput) {
    const v = (nameInput.value || nameInput.getAttribute('value') || '').trim();
    if (v) result.product_name = v;
  }

  // 发送元 文本块
  const senderEl = xpath('/html/body/div[2]/div[2]/main/div/div[2]/div[2]/form/div[5]/div[2]');
  if (senderEl) {
    const t = tx(senderEl);
    if (t) result.sender_address = t;
  }

  // 当前发送方式 banner 文本
  const banner = xpath('/html/body/div[2]/div[2]/main/div/div[2]/div[2]/form/aside[1]/div/div[1]/div[2]/p');
  if (banner) {
    const t = tx(banner);
    if (t) result.current_shipping_status = t;
  }

  // 通过文本查找按钮可用性
  const allClickables = Array.from(document.querySelectorAll('button, a, [role="button"]'));
  result.has_size_location_btn = allClickables.some(b => (b.innerText || '').includes('商品サイズと発送場所'));
  result.has_change_method_btn = allClickables.some(b => (b.innerText || '').includes('発送方法を変更'));

  // 消息流：拆分 from / text / at
  // 每条消息的 innerText 通常形如：
  //   月雫\nこんにちは...\nよろしくお願い致します\n5時間前\n報告する
  // 启发：第 1 行短文本视为 from；末尾若是「報告する」「違反内容を報告」剔除；
  // 倒数第 N 行匹配「N 分前 / N 時間前 / N 日前 / N ヶ月前 / 数字年前」视为 at
  const msgRoot = xpath('/html/body/div[2]/div[2]/main/div/div[2]/div[5]/div[2]');
  if (msgRoot) {
    const items = Array.from(msgRoot.children).filter(el => tx(el));
    const timeRe = /^\d+\s*(分前|時間前|日前|ヶ月前|年前)$/;
    const reportRe = /^(報告する|違反内容を報告)$/;
    for (const item of items) {
      let lines = tx(item).split('\n').map(s => s.trim()).filter(Boolean);
      if (!lines.length) continue;
      // 剔除尾部「報告する」
      while (lines.length && reportRe.test(lines[lines.length - 1])) lines.pop();
      // 取尾部相对时间
      let at = null;
      while (lines.length && timeRe.test(lines[lines.length - 1])) {
        at = lines[lines.length - 1];
        lines.pop();
      }
      // 取首行作为 from（短文本视为名字，且后面还有正文）
      let from = null;
      if (lines.length >= 2 && lines[0].length <= 32) {
        from = lines[0];
        lines = lines.slice(1);
      }
      const text = lines.join('\n').trim();
      if (text || from) {
        result.messages.push({ from, text, at });
      }
    }
    if (result.messages.length === 0) {
      const all = tx(msgRoot);
      if (all) result.messages.push({ from: null, text: all, at: null });
    }
  }

  // 左侧 sidebar 字段：按标签文本就近匹配下一个兄弟节点
  function findValueByLabel(label) {
    const cands = Array.from(document.querySelectorAll('dt, th, span, p, div, label'));
    for (const el of cands) {
      const direct = (el.firstChild && el.firstChild.nodeType === 3 ? el.firstChild.nodeValue : '').trim();
      if (direct === label) {
        if (el.tagName === 'DT' && el.nextElementSibling && el.nextElementSibling.tagName === 'DD') return tx(el.nextElementSibling);
        if (el.tagName === 'TH' && el.nextElementSibling && el.nextElementSibling.tagName === 'TD') return tx(el.nextElementSibling);
        if (el.nextElementSibling) return tx(el.nextElementSibling);
        if (el.parentElement) {
          const sibs = Array.from(el.parentElement.children).filter(c => c !== el);
          if (sibs.length) return tx(sibs[sibs.length - 1]);
        }
      }
    }
    return null;
  }
  result.price = parseYen(findValueByLabel('商品代金'));
  result.fee = parseYen(findValueByLabel('販売手数料'));
  result.profit = parseYen(findValueByLabel('販売利益'));
  result.shipping_fee_label = findValueByLabel('送料');
  result.purchase_time = findValueByLabel('購入日時');
  result.delivery_method = findValueByLabel('配送の方法');

  // 购入者
  const buyerHdr = Array.from(document.querySelectorAll('h2, h3, h4, dt, p, span, div'))
    .find(el => (el.firstChild && el.firstChild.nodeType === 3 ? el.firstChild.nodeValue : '').trim() === '購入者情報');
  if (buyerHdr) {
    const region = buyerHdr.nextElementSibling || (buyerHdr.parentElement && buyerHdr.parentElement.nextElementSibling);
    if (region) {
      const fullTxt = tx(region);
      const lines = fullTxt.split('\n').map(s => s.trim()).filter(Boolean);
      if (lines.length) result.buyer_name = lines[0];
      result.buyer_verified = fullTxt.includes('本人確認済');
    }
  }

  return result;
}
"""


# 抓取前等 SPA 渲染：transaction 页面 JS bundle + 异步请求落定通常 1.5～3 秒
_RENDER_WAIT_SEC = 3.0


async def fetch_transaction_detail(todo_id: int) -> Dict[str, Any]:
    """打开有头浏览器到 transaction 页，提取关键字段并返回。

    浏览器不会自动关闭——保留给用户在原生页面继续操作。
    """
    todo = TodoItemModel.find_by_id(id=int(todo_id))
    if not todo:
        raise ValueError(f"代办事项 id={todo_id} 不存在")

    item_id = (todo.item_id or "").strip()
    if not item_id:
        raise ValueError("该代办无关联 item_id，无法打开交易页")

    aid = int(todo.account_id)
    url = f"https://jp.mercari.com/transaction/{item_id}"
    log.info("[txdetail] 打开交易页 account_id=%s url=%s", aid, url)

    r = start_mitm_proxy()
    if r.get("error"):
        raise RuntimeError(f"MITM 代理不可用: {r['error']}")

    try:
        seed_automation_profile_from_account(aid)
    except Exception as exc:
        log.warning("[txdetail] seed __auto profile 失败（继续，使用磁盘旧 Cookie）：%s", exc)

    mgr = get_web_drive_manager()
    auto_key = meilu_automation_key(aid)
    proxy = default_mitm_proxy_url()

    # 启动有头非最小化窗口；ensure_session_for_mitm 内部会关掉旧的 __auto
    await mgr.ensure_session_for_mitm(
        auto_key,
        start_url=url,
        proxy_server=proxy,
        headless=False,
        start_minimized=False,
        block_images=False,  # 用户要看页面，允许加载图片
    )

    # 兜底再 goto 一次（ensure_session_for_mitm 已带 start_url，但偶发未完成跳转）
    try:
        await mgr.reload_active_tab(auto_key, url)
    except Exception as exc:
        log.warning("[txdetail] reload_active_tab 失败（忽略）：%s", exc)

    await asyncio.sleep(_RENDER_WAIT_SEC)

    try:
        page = await mgr.active_tab_page(auto_key)
        data = await page.evaluate(_EXTRACT_JS)
    except Exception as exc:
        log.exception("[txdetail] DOM 提取失败：%s", exc)
        data = {}

    return {
        "todo_id": int(todo_id),
        "account_id": aid,
        "item_id": item_id,
        "url": url,
        **(data if isinstance(data, dict) else {}),
    }
