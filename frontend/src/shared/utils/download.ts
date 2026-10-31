// 受保护文件的下载：带 token 拉取 blob 后触发浏览器下载。
// 优先使用后端返回的 Content-Disposition 文件名。

import { getToken } from '@/shared/api/client'

export async function downloadAuthed(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ''}` },
  })
  if (!res.ok) {
    throw new Error('下载失败，请稍后重试')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)

  const disposition = res.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/)
  const name = encoded ? decodeURIComponent(encoded[1]) : fallbackName

  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
