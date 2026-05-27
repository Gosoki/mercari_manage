import http from './http'

// 备忘录 / 站内信 → /mercariV2/src/use_web/memos/*
export const memosApi = {
  /** 收件箱（接收方 = 当前用户） */
  inbox: (params) => http.get('/use_web/memos/inbox', { params }),
  /** 已发送（发送方 = 当前用户） */
  sent: (params) => http.get('/use_web/memos/sent', { params }),
  /** 可发送备忘录的用户列表（排除自己 + 已禁用） */
  users: () => http.get('/use_web/memos/users'),
  /** 未读数量 */
  unreadCount: () => http.get('/use_web/memos/unread-count'),
  /** 发送新备忘录 */
  create: (data) => http.post('/use_web/memos', data),
  /** 上传单张图片：返回 { path: '/imges/memo_xxx.jpg' } */
  uploadImage: (file) => {
    const fd = new FormData()
    fd.append('file', file, file?.name || 'memo.jpg')
    return http.post('/use_web/memos/upload-image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },
  /** 标记已读 / 未读（ids + is_read） */
  markRead: (ids, is_read = true) =>
    http.post('/use_web/memos/mark-read', { ids, is_read }),
  /** 一键全部标记已读 */
  markAllRead: () => http.post('/use_web/memos/mark-all-read'),
  /** 删除（发送方或接收方均可） */
  remove: (id) => http.delete(`/use_web/memos/${id}`),
}
