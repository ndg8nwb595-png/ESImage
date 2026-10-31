// 聊天轻链路 SSE 客户端：POST 后读取 text/event-stream，按事件回调。
// 服务端事件：meta / agent_status / delta / done（见 backend sessions.py）。

import { getToken } from '@/shared/api/client'

export interface SSEHandlers {
  onMeta?: (data: { message_id: number; session_id: number }) => void
  onAgentStatus?: (data: { agent_code: string; status: string }) => void
  onDelta?: (data: { content: string }) => void
  onDone?: (data: Record<string, unknown>) => void
}

interface SSEBlock {
  event: string
  data: unknown
}

/** 把累积的文本块解析成 SSE 事件；返回消费到的完整块。 */
export function parseSSEBlocks(buffer: string): { blocks: SSEBlock[]; rest: string } {
  const blocks: SSEBlock[] = []
  let rest = buffer
  let boundary = rest.indexOf('\n\n')
  while (boundary >= 0) {
    const raw = rest.slice(0, boundary)
    rest = rest.slice(boundary + 2)
    let event = 'message'
    let dataRaw = ''
    for (const line of raw.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataRaw += line.slice(5).trim()
    }
    if (dataRaw) {
      try {
        blocks.push({ event, data: JSON.parse(dataRaw) })
      } catch {
        // 非法 JSON 块跳过，避免中断整条流
      }
    }
    boundary = rest.indexOf('\n\n')
  }
  return { blocks, rest }
}

export async function postSSE(
  path: string,
  body: unknown,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok || !res.body) {
    const envelope = (await res.json().catch(() => null)) as { message?: string } | null
    throw new Error(envelope?.message ?? '请求失败，请稍后重试')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { blocks, rest } = parseSSEBlocks(buffer)
    buffer = rest
    for (const block of blocks) {
      dispatch(block, handlers)
    }
  }
}

function dispatch(block: SSEBlock, handlers: SSEHandlers): void {
  const data = block.data as Record<string, unknown>
  switch (block.event) {
    case 'meta':
      handlers.onMeta?.(data as never)
      break
    case 'agent_status':
      handlers.onAgentStatus?.(data as never)
      break
    case 'delta':
      handlers.onDelta?.(data as never)
      break
    case 'done':
      handlers.onDone?.(data)
      break
  }
}
