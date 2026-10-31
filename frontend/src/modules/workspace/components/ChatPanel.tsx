import { SendOutlined } from '@ant-design/icons'
import { Button, Empty, Input, Spin } from 'antd'
import { useEffect, useRef, useState } from 'react'

import { postSSE } from '@/shared/api/sse'
import type { ChatMessage } from '@/shared/types'
import { useWorkspaceStore } from '../store'

const AGENT_LABELS: Record<string, string> = {
  planner: '规划意图',
  product_understanding: '理解商品',
}

/** 中栏：聊天框（轻链路 SSE）。 */
export default function ChatPanel() {
  const params = useWorkspaceStore((s) => s.params)
  const currentSessionId = useWorkspaceStore((s) => s.currentSessionId)
  const messages = useWorkspaceStore((s) => s.messages)
  const messagesLoading = useWorkspaceStore((s) => s.messagesLoading)

  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [agentStatus, setAgentStatus] = useState<string | null>(null)
  const streamRef = useRef('')
  const endRef = useRef<HTMLDivElement>(null)

  const canChat = params.product_name.trim().length > 0

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, agentStatus])

  const onSend = async () => {
    const content = input.trim()
    if (!content || !canChat || sending) return
    setInput('')
    setSending(true)
    setStreamingText('')
    setAgentStatus(null)
    streamRef.current = ''

    const store = useWorkspaceStore.getState()
    const clientMessageId = crypto.randomUUID()

    const userMessage: ChatMessage = {
      message_id: -Date.now(),
      session_id: currentSessionId ?? 0,
      role: 'user',
      agent_code: null,
      content,
      content_type: 'text',
      status: 'done',
      token_in: null,
      token_out: null,
      created_at: new Date().toISOString(),
    }
    store.setMessages([...store.messages, userMessage])

    const path = currentSessionId
      ? `/sessions/${currentSessionId}/messages`
      : '/sessions/messages'

    try {
      await postSSE(
        path,
        {
          client_message_id: clientMessageId,
          content,
          session_id: currentSessionId ?? null,
          params: {
            product_name: params.product_name,
            style_text: params.style_text,
            width: params.width,
            height: params.height,
            template_id: params.template_id,
          },
        },
        {
          onMeta: ({ session_id }) => {
            const st = useWorkspaceStore.getState()
            st.setCurrentSession(session_id)
            void st.loadSessions()
          },
          onAgentStatus: ({ agent_code, status }) => {
            setAgentStatus(status === 'started' ? (AGENT_LABELS[agent_code] ?? agent_code) : null)
          },
          onDelta: ({ content: delta }) => {
            streamRef.current += delta
            setStreamingText(streamRef.current)
          },
          onDone: () => {
            const st = useWorkspaceStore.getState()
            const assistantMessage: ChatMessage = {
              message_id: -Date.now(),
              session_id: st.currentSessionId ?? 0,
              role: 'assistant',
              agent_code: 'product_understanding',
              content: streamRef.current,
              content_type: 'text',
              status: 'done',
              token_in: null,
              token_out: null,
              created_at: new Date().toISOString(),
            }
            st.setMessages([...st.messages, assistantMessage])
            void st.loadSessions()
          },
        },
      )
    } catch {
      // 发送失败：由 UI 提示，不吞掉已追加的用户消息
      setAgentStatus('发送失败，请重试')
    } finally {
      setSending(false)
      setStreamingText('')
      streamRef.current = ''
    }
  }

  return (
    <section className="ws-col ws-chat">
      <div className="ws-chat-messages">
        {messagesLoading ? (
          <div style={{ textAlign: 'center', marginTop: 40 }}>
            <Spin />
          </div>
        ) : messages.length === 0 && !streamingText ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={canChat ? '开始和 AI 聊聊你的需求' : '请先在右侧填写商品名称'}
            style={{ marginTop: 60 }}
          />
        ) : (
          <>
            {messages.map((m) => (
              <div key={m.message_id} className={`msg-row ${m.role}`}>
                <div className={`msg-bubble ${m.role}`}>{m.content}</div>
              </div>
            ))}
            {streamingText && (
              <div className="msg-row assistant">
                <div className="msg-bubble assistant">
                  {streamingText}
                  {agentStatus && <span style={{ color: '#6b7280' }}>…</span>}
                </div>
              </div>
            )}
          </>
        )}
        <div ref={endRef} />
      </div>

      <div className="ws-chat-input">
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={!canChat}
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder={canChat ? '补充卖点、目标人群、使用场景…（Enter 发送，Shift+Enter 换行）' : '请先在右侧填写商品名称'}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              void onSend()
            }
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
          <Button
            type="primary"
            icon={<SendOutlined />}
            disabled={!canChat || !input.trim() || sending}
            loading={sending}
            onClick={() => void onSend()}
          >
            发送
          </Button>
        </div>
      </div>
    </section>
  )
}
