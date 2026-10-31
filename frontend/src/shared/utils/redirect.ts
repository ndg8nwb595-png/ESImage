// 登录回跳安全校验：只接受以单个 `/` 开头、且不以 `//` 开头的站内路径。
// 含协议、域名、反斜杠或 `..` 的值一律忽略（接口文档 §5.3）。

export function parseSafeRedirect(raw: string | null | undefined): string | null {
  if (!raw) return null
  const value = raw.trim()
  if (!value.startsWith('/') || value.startsWith('//')) return null
  if (value.includes('\\') || value.includes('..')) return null
  // 只允许合法站内路径字符，排除协议与域名形态
  if (!/^\/[A-Za-z0-9_\-/]*(\?[A-Za-z0-9_\-=&%.]*)?$/.test(value)) return null
  return value
}

/** 按角色组合决定默认落地页（接口文档 §5.4）。 */
export function defaultLandingPath(roles: string[]): string {
  const hasUser = roles.includes('user')
  const hasAdmin = roles.includes('admin') || roles.includes('super_admin')
  // 仅管理员/超管进入管理后台，否则进创作工作台
  if (!hasUser && hasAdmin) return '/admin/dashboard'
  return '/workspace'
}
