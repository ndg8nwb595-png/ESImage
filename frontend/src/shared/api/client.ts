// fetch 封装：统一注入 Authorization、JSON 头、解析统一响应、映射业务错误码。
// 401/403 按接口文档 §5.2 约定做全局处理（清除登录态并跳转）。

import { useAuthStore } from '@/shared/store/authStore'
import { getToken, setToken, TOKEN_KEY } from './token'

// 供其余模块继续从 client 统一导入 token 工具
export { getToken, setToken, TOKEN_KEY }

/** 业务错误：携带 HTTP 状态与业务 code。 */
export class ApiError extends Error {
  readonly status: number
  readonly code: number

  constructor(status: number, code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface Envelope<T> {
  code: number
  message: string
  data: T
}

/** 401/403 全局登出与回跳处理（20005 无权限除外）。 */
function handleAuthFailure(status: number, code: number): void {
  // 20002 登录已过期 / 20003 token 无效 / 20004 账号不可用：清除登录态回登录页
  if ((status === 401 && (code === 20002 || code === 20003)) || (status === 403 && code === 20004)) {
    useAuthStore.getState().clear()
    const path = window.location.pathname + window.location.search
    window.location.href = `/login?redirect=${encodeURIComponent(path)}`
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  // FormData 上传不手动设置 Content-Type，交给浏览器带 boundary
  if (!(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, -1, '网络异常，请稍后重试')
  }

  const body = (await res.json().catch(() => null)) as Envelope<T> | null
  const code = body?.code ?? -1
  const message = body?.message ?? '系统繁忙，请稍后重试'

  if (!res.ok) {
    handleAuthFailure(res.status, code)
    throw new ApiError(res.status, code, message)
  }
  return body!.data
}
