import http from './http'

// 数据库管理（SQLite / MySQL 切换 + 数据迁移）
// → /mercariV2/src/use_web/system/database/*
export const databaseApi = {
  // 当前后端与 MySQL 连接配置（密码不回传，仅返回 password_set）
  getConfig: () => http.get('/use_web/system/database/config'),
  // 测试 MySQL 连接（密码留空则沿用已保存密码）
  testConnection: (params) => http.post('/use_web/system/database/test-connection', params),
  // 切换后端：迁移数据 + 保存选择 + 自动重启（迁移可能较久，放宽超时）
  switch: (payload) => http.post('/use_web/system/database/switch', payload, { timeout: 300000 })
}
