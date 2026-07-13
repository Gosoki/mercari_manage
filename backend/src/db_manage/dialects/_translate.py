# -*- coding: utf-8 -*-
"""SQLite 风格 SQL → MySQL 语法翻译。

上层统一以 SQLite 风格书写 SQL：
  · 参数占位符使用 ``?``
  · 标识符引用使用 ``[名称]`` 方括号

本模块把这类 SQL 翻译为 MySQL/PyMySQL 语法：
  · ``[名称]`` → `` `名称` ``（反引号）
  · ``?``     → ``%s``
  · 当带参数执行时，PyMySQL 会对整条 SQL 做一次 ``%`` 格式化，
    因此原文中所有字面量 ``%`` 必须先转义为 ``%%``（包括字符串字面量内部）。

翻译需要区分「字符串字面量内部」与「SQL 语法部分」：仅在语法部分做
``[]``/``?`` 替换，避免误伤字符串里的方括号或问号。字符串字面量以单引号
界定，``''`` 表示转义的单引号。
"""

from __future__ import annotations


def _convert_brackets_and_params(sql: str) -> str:
    """把语法部分的 ``[id]``→`` `id` ``、``?``→``%s``，跳过 '...' 字符串字面量。"""
    out = []
    i = 0
    n = len(sql)
    in_str = False
    while i < n:
        c = sql[i]
        if in_str:
            out.append(c)
            if c == "'":
                # 连续两个单引号是转义的字面单引号，仍在字符串内
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_str = False
            i += 1
            continue
        # 语法部分
        if c == "'":
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "[":
            j = sql.find("]", i + 1)
            if j == -1:  # 不成对，原样输出
                out.append(c)
                i += 1
                continue
            ident = sql[i + 1:j]
            out.append("`" + ident + "`")
            i = j + 1
            continue
        if c == "?":
            out.append("%s")
            i += 1
            continue
        out.append(c)
        i += 1
    return out and "".join(out) or ""


def translate(sql: str, has_params: bool) -> str:
    """把 SQLite 风格 SQL 翻译为 MySQL 语法。

    ``has_params`` 为 True（execute/executemany 带参数）时，PyMySQL 会对
    整条 SQL 执行 ``query % args``，故需先把所有字面量 ``%`` 转义为 ``%%``；
    随后再由 ``?`` 生成干净的 ``%s`` 占位符。
    """
    if has_params and "%" in sql:
        sql = sql.replace("%", "%%")
    return _convert_brackets_and_params(sql)
