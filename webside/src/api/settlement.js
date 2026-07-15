import http from './http'

// 结算（System 二级页面）→ /mercariV2/src/use_web/system/settlement/*
export const settlementApi = {
  // params: { start, end, by_purchase_time }（start/end 为 unix 秒）
  summary: (params) => http.get('/use_web/system/settlement/summary', { params })
}
