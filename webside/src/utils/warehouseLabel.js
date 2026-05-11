/** 下拉与简短展示：有货架名称时为「名称（货架号）」；货架号可空 */
export function warehouseShelfLabel(w) {
  if (!w) return ''
  const code = w.name != null && String(w.name).trim() ? String(w.name).trim() : ''
  const title = (w.shelf_name || '').trim()
  if (title && code) return `${title}（${code}）`
  if (title) return title
  if (code) return code
  return '（未设货架号）'
}
