/** 货架位主键（warehouses.id）展示 */
export function warehouseShelfPrimaryKey(w) {
  if (w?.id == null || w.id === '') return ''
  return String(w.id)
}

/** 下拉与简短展示：有货架名称时为「名称（货架号）」；末尾附主键 #id 便于区分重复货架号 */
export function warehouseShelfLabel(w) {
  if (!w) return ''
  const pk = warehouseShelfPrimaryKey(w)
  const pkSuffix = pk ? ` #${pk}` : ''
  const code = w.name != null && String(w.name).trim() ? String(w.name).trim() : ''
  const title = (w.shelf_name || '').trim()
  if (title && code) return `${title}（${code}）${pkSuffix}`
  if (title) return `${title}${pkSuffix}`
  if (code) return `${code}${pkSuffix}`
  return pk ? `（未设货架号） #${pk}` : '（未设货架号）'
}

/** 级联选择器叶子节点：货架号 + 主键 */
export function warehouseShelfLeafLabel(w) {
  if (!w) return ''
  const code = w.name != null && String(w.name).trim() ? String(w.name).trim() : '（未设货架号）'
  const pk = warehouseShelfPrimaryKey(w)
  return pk ? `${code} #${pk}` : code
}
