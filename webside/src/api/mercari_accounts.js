import http from './http'

// 煤炉账号 → /mercariV2/src/use_web/mercari-accounts/*
export const mercariAccountApi = {
  list: (params) => http.get('/use_web/mercari-accounts', { params }),
  create: (data) => http.post('/use_web/mercari-accounts', data),
  update: (id, data) => http.put(`/use_web/mercari-accounts/${id}`, data),
  remove: (id) => http.delete(`/use_web/mercari-accounts/${id}`),
  /** MITM 抓取 items/get_items(trading) 请求头并写回账号（可能较久，timeout: 0） */
  fetchAuthViaMitm: (id, axiosConfig = {}) =>
    http.post(`/use_web/mercari-accounts/${id}/fetch-auth-via-mitm`, {}, { timeout: 0, ...axiosConfig }),
  /**
   * 打开出品一覧页，MITM 截获 items/get_items（on_sale,stop）并解析 seller_id。
   * account_key: mercari_prepare（新增）或 mercari_{id}（编辑）
   */
  fetchSellerIdViaMitm: (data, axiosConfig = {}) =>
    http.post('/use_web/mercari-accounts/fetch-seller-id-via-mitm', data, { timeout: 0, ...axiosConfig })
}
