// 受保护的图片：后端图片接口要求 Authorization 头，<img> 无法直接携带，
// 这里用带 token 的 fetch 拉成 blob URL 再渲染。加载前占位避免布局抖动。

import { useEffect, useState } from 'react'

import { getToken } from '@/shared/api/client'

interface Props {
  src: string | null
  alt?: string
  className?: string
}

export default function AuthedImage({ src, alt = '', className }: Props) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!src) {
      setUrl(null)
      return
    }
    let objectUrl: string | null = null
    let cancelled = false
    fetch(src, { headers: { Authorization: `Bearer ${getToken() ?? ''}` } })
      .then((res) => {
        if (!res.ok) throw new Error('加载失败')
        return res.blob()
      })
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setUrl(null)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src])

  if (!url) {
    return <div className={className ?? 'img-fixed'} aria-label={alt || '图片加载中'} />
  }
  return <img src={url} alt={alt} className={className} />
}
