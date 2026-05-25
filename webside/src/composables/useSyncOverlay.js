import { reactive } from 'vue'

/**
 * 通用「正在调用浏览器自动化」全屏等待覆盖层 + 进度轮询。
 *
 * 用法：
 *   const overlay = useSyncOverlay()
 *   // 模板里：<SyncOverlay :state="overlay.state" />
 *   await overlay.run({
 *     title: '正在拉取交易详情',
 *     consoleTag: '[交易详情]',
 *     pollFn: (jobId) => someApi.getProgress(jobId),
 *     actionFn: (jobId) => someApi.doSomething(id, { progress_job_id: jobId }),
 *   })
 *
 * - pollFn 缺省 / 返回为空时仍可展示标题（只是没有具体步骤文案）
 * - 业务抛错时会自动展示「<title>失败」+ 错误信息 1.2s 后再关闭
 */
export function useSyncOverlay() {
  const state = reactive({
    visible: false,
    title: '',
    failed: false,
    label: '',
  })
  let timer = null

  function generateJobId() {
    return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `job_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
  }

  async function run({ title, failedTitle, consoleTag, pollFn, actionFn, errorHoldMs = 1200 }) {
    if (typeof actionFn !== 'function') {
      throw new Error('useSyncOverlay.run: actionFn is required')
    }
    const jobId = generateJobId()
    let lastStep = ''
    const poll = async () => {
      if (typeof pollFn !== 'function') return
      try {
        const pr = await pollFn(jobId)
        const zh = pr?.data?.label_zh
        if (zh) {
          state.label = zh
          if (consoleTag && zh !== lastStep) {
            lastStep = zh
            try { console.log(consoleTag, zh) } catch {}
          }
        }
      } catch { /* 轮询失败忽略 */ }
    }

    state.title = title || '正在处理'
    state.failed = false
    state.label = '正在连接服务器…'
    state.visible = true
    if (typeof pollFn === 'function') {
      await poll()
      timer = setInterval(poll, 400)
    }

    let hadError = false
    try {
      return await actionFn(jobId)
    } catch (e) {
      hadError = true
      state.failed = true
      state.title = failedTitle || `${title || '操作'}失败`
      state.label = e?.response?.data?.detail || e?.message || '操作失败'
      throw e
    } finally {
      if (timer != null) {
        clearInterval(timer)
        timer = null
      }
      if (hadError && errorHoldMs > 0) {
        await new Promise((r) => setTimeout(r, errorHoldMs))
      }
      state.visible = false
      state.title = ''
      state.failed = false
      state.label = ''
    }
  }

  function dispose() {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
  }

  return { state, run, dispose }
}
