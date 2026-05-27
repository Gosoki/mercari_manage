#!/usr/bin/env node
// 从 git HEAD 恢复每个 .vue 文件的 <script setup> 内容，
// 重新包装为 defineComponent({ setup() { ...原逻辑; return {...} } }) 写入对应 views/X/script.js。

import { execSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..')
const VIEWS_REL = 'webside/src/views'

// 映射：原 .vue 路径 -> 新 script.js 路径
const targets = [
  ['Login.vue',                                    'Login/script.js'],
  ['Dashboard.vue',                                'Dashboard/script.js'],
  ['Inventory.vue',                                'Inventory/script.js'],
  ['Orders.vue',                                   'Orders/script.js'],
  ['OnSaleItems.vue',                              'OnSaleItems/script.js'],
  ['Todos.vue',                                    'Todos/script.js'],
  ['Notifications.vue',                            'Notifications/script.js'],
  ['MercariAccounts.vue',                          'MercariAccounts/script.js'],
  ['system/System.vue',                            'system/System/script.js'],
  ['system/Categories.vue',                        'system/Categories/script.js'],
  ['system/ProductTypeCategoryMappings.vue',       'system/ProductTypeCategoryMappings/script.js'],
  ['system/Warehouses.vue',                        'system/Warehouses/script.js'],
  ['system/Transactions.vue',                      'system/Transactions/script.js'],
  ['system/CostRecords.vue',                       'system/CostRecords/script.js'],
  ['system/CostExpenses.vue',                      'system/CostExpenses/script.js'],
]

function gitShow(relPath) {
  // 用 Buffer 输出避免 PowerShell 编码问题
  const buf = execSync(`git show HEAD:${VIEWS_REL}/${relPath}`, { cwd: REPO_ROOT, encoding: 'buffer', maxBuffer: 100 * 1024 * 1024 })
  return buf.toString('utf8')
}

function extractScriptSetup(vueSrc) {
  const m = /<script\s+setup[^>]*>([\s\S]*?)<\/script>/m.exec(vueSrc)
  if (!m) throw new Error('未找到 <script setup>')
  return m[1].replace(/^\n+/, '').replace(/\n+$/, '\n')
}

// 把 setup 体拆为 imports 前缀和实际 body
function splitImports(src) {
  const lines = src.split('\n')
  const imports = []
  const body = []
  let inImport = false
  let buf = ''
  for (const line of lines) {
    if (!inImport && /^\s*import\b/.test(line)) {
      inImport = true
      buf = line + '\n'
      if (/from\s+['"][^'"]+['"]\s*;?\s*$/.test(line.trim()) || (!/['"]$/.test(line.trim()) && /;\s*$/.test(line.trim()))) {
        imports.push(buf.trimEnd())
        inImport = false; buf = ''
      }
      continue
    }
    if (inImport) {
      buf += line + '\n'
      if (/from\s+['"][^'"]+['"]\s*;?\s*$/.test(line.trim())) {
        imports.push(buf.trimEnd())
        inImport = false; buf = ''
      }
      continue
    }
    body.push(line)
  }
  return { imports: imports.join('\n'), body: body.join('\n').replace(/^\n+/, '') }
}

function splitTopLevelCommas(str) {
  const out = []
  let depth = 0
  let cur = ''
  let inStr = null
  for (let i = 0; i < str.length; i++) {
    const c = str[i]
    if (inStr) {
      if (c === '\\') { cur += c + (str[i + 1] || ''); i++; continue }
      if (c === inStr) inStr = null
      cur += c
      continue
    }
    if (c === '"' || c === "'" || c === '`') { inStr = c; cur += c; continue }
    if (c === '{' || c === '(' || c === '[') depth++
    else if (c === '}' || c === ')' || c === ']') depth--
    if (c === ',' && depth === 0) { out.push(cur); cur = ''; continue }
    cur += c
  }
  if (cur.trim()) out.push(cur)
  return out
}

// 每行起始的括号深度（{}()/[] 都计入）
function computeLineDepths(body) {
  const depths = [0]
  let d = 0, inStr = null, inLine = false, inBlock = false
  for (let i = 0; i < body.length; i++) {
    const c = body[i], next = body[i + 1]
    if (c === '\n') { depths.push(d); inLine = false; continue }
    if (inLine) continue
    if (inBlock) { if (c === '*' && next === '/') { inBlock = false; i++ }; continue }
    if (inStr) {
      if (c === '\\') { i++; continue }
      if (c === inStr) inStr = null
      continue
    }
    if (c === '/' && next === '/') { inLine = true; i++; continue }
    if (c === '/' && next === '*') { inBlock = true; i++; continue }
    if (c === '"' || c === "'" || c === '`') { inStr = c; continue }
    if (c === '{' || c === '(' || c === '[') d++
    else if (c === '}' || c === ')' || c === ']') d--
  }
  return depths
}

function extractImportNames(importsText) {
  const out = []
  const seen = new Set()
  const add = (n) => { if (n && !seen.has(n)) { seen.add(n); out.push(n) } }
  // 逐条匹配 import ... from '...'
  const re = /import\s+([\s\S]*?)\s+from\s+['"][^'"]+['"]/g
  let m
  while ((m = re.exec(importsText)) !== null) {
    let spec = m[1].trim()
    // import 'side-effect' — re 不会匹配（无 from）
    // 处理 default、命名、命名空间
    // 形态：A | { a, b as c } | * as ns | A, { a, b } | A, * as ns
    const parts = []
    // 切出花括号块
    const braceMatch = /\{([\s\S]*?)\}/.exec(spec)
    if (braceMatch) {
      const named = braceMatch[1]
      for (const item of named.split(',')) {
        const it = item.trim()
        if (!it) continue
        const asMatch = /^(?:[A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)/.exec(it)
        if (asMatch) parts.push(asMatch[1])
        else {
          const simple = /^([A-Za-z_$][\w$]*)/.exec(it)
          if (simple) parts.push(simple[1])
        }
      }
      spec = spec.replace(braceMatch[0], '').trim()
    }
    // 去除尾部空逗号
    spec = spec.replace(/^,|,$/g, '').trim()
    // 剩余可能是 default 和/或 * as ns，逗号分隔
    for (const item of spec.split(',')) {
      const it = item.trim()
      if (!it) continue
      const nsMatch = /^\*\s+as\s+([A-Za-z_$][\w$]*)/.exec(it)
      if (nsMatch) { parts.push(nsMatch[1]); continue }
      const def = /^([A-Za-z_$][\w$]*)/.exec(it)
      if (def) parts.push(def[1])
    }
    for (const p of parts) add(p)
  }
  return out
}

function extractTopLevelIds(body) {
  const ids = []
  const seen = new Set()
  const add = (id) => { if (id && !seen.has(id)) { seen.add(id); ids.push(id) } }
  const lines = body.split('\n')
  const depths = computeLineDepths(body)
  for (let i = 0; i < lines.length; i++) {
    if ((depths[i] ?? 0) !== 0) continue
    const trimmed = lines[i].trim()
    if (!trimmed) continue

    let m = /^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/.exec(trimmed)
    if (m) { add(m[1]); continue }

    m = /^(?:export\s+)?(?:const|let|var)\s+(.+?)(?:=|$)/.exec(trimmed)
    if (!m) continue
    const decl = m[1].trim()
    for (const part of splitTopLevelCommas(decl)) {
      const p = part.trim().replace(/=.*$/, '').trim()
      if (!p) continue
      if (p.startsWith('{')) {
        const inner = p.replace(/^\{|\}\s*$/g, '')
        for (const item of splitTopLevelCommas(inner)) {
          const it = item.trim().replace(/=.*$/, '').trim()
          if (!it) continue
          if (it.startsWith('...')) {
            const m2 = /^\.{3}\s*([A-Za-z_$][\w$]*)/.exec(it)
            if (m2) add(m2[1])
            continue
          }
          const renamed = /:\s*([A-Za-z_$][\w$]*)/.exec(it)
          if (renamed) { add(renamed[1]); continue }
          const simple = /^([A-Za-z_$][\w$]*)/.exec(it)
          if (simple) add(simple[1])
        }
      } else if (p.startsWith('[')) {
        const inner = p.replace(/^\[|\]\s*$/g, '')
        for (const item of splitTopLevelCommas(inner)) {
          const it = item.trim().replace(/=.*$/, '').trim()
          if (!it) continue
          if (it.startsWith('...')) {
            const m2 = /^\.{3}\s*([A-Za-z_$][\w$]*)/.exec(it)
            if (m2) add(m2[1])
            continue
          }
          const simple = /^([A-Za-z_$][\w$]*)/.exec(it)
          if (simple) add(simple[1])
        }
      } else {
        const simple = /^([A-Za-z_$][\w$]*)/.exec(p)
        if (simple) add(simple[1])
      }
    }
  }
  return ids
}

function rebuild(vueRel, jsRel) {
  const vueSrc = gitShow(vueRel)
  const setupBody = extractScriptSetup(vueSrc)
  const { imports, body } = splitImports(setupBody)
  const bodyIds = extractTopLevelIds(body)

  let importsOut = imports
  if (!/\bdefineComponent\b/.test(importsOut)) {
    if (/\bfrom\s+['"]vue['"]/.test(importsOut)) {
      importsOut = importsOut.replace(/import\s*\{([^}]*)\}\s*from\s*['"]vue['"]/,
        (_, inner) => `import { defineComponent,${inner}} from 'vue'`)
    } else {
      importsOut = `import { defineComponent } from 'vue'\n` + importsOut
    }
  }

  // 同时把所有 import 名（除 defineComponent 外）加入 return,
  // 因为 <script setup> 会自动把它们暴露给模板,
  // 而 Options API 必须显式 return 才能让模板访问。
  const importNames = extractImportNames(importsOut).filter(n => n !== 'defineComponent')
  const ids = [...importNames, ...bodyIds.filter(id => !importNames.includes(id))]

  const indented = body.split('\n').map(l => l ? '    ' + l : l).join('\n')
  const returnBlock = ids.length
    ? `    return {\n${ids.map(id => `      ${id},`).join('\n')}\n    }\n`
    : '    return {}\n'

  const out = `${importsOut}\n\nexport default defineComponent({\n  setup() {\n${indented}\n${returnBlock}  },\n})\n`

  const outPath = join(REPO_ROOT, VIEWS_REL, jsRel)
  writeFileSync(outPath, out, 'utf8')
  console.log(`[rebuild] ${jsRel} - ${ids.length} 个绑定`)
}

for (const [vueRel, jsRel] of targets) rebuild(vueRel, jsRel)
console.log('完成')
