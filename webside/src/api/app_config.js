import http from './http'

// 应用配置（系统页：出品默认值）→ /mercariV2/src/use_web/system/listing-defaults
export const configApi = {
  getListingDefaults: () => http.get('/use_web/system/listing-defaults'),
  putListingDefaults: (data) => http.put('/use_web/system/listing-defaults', data),
  // 自动出品总开关 → /mercariV2/src/use_web/system/auto-listing-master
  getAutoListingMaster: () => http.get('/use_web/system/auto-listing-master'),
  putAutoListingMaster: (data) => http.put('/use_web/system/auto-listing-master', data)
}
