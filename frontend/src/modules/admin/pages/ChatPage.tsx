import { App, Button, Card, Collapse, Input, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'

import { formatDateTime } from '@/shared/utils/time'
import * as api from '../content/api'
import type { ChatSessionDetail, ChatSessionItem } from '../content/api'

/** 聊天记录：会话列表 + 会话详情（消息 + Agent 调用明细）。 */
export default function ChatPage() {
  const { message } = App.useApp()
  const [data, setData] = useState<api.Paged<ChatSessionItem> | null>(null)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ user_keyword: '', title_keyword: '', status: 'all' })
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null)

  const load = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      setData(await api.chatSessions({ ...filters, page: p, page_size: 20 }))
      setPage(p)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [filters, message])

  useEffect(() => { void load(1) }, [load])

  const openDetail = async (sessionId: number) => {
    try {
      setDetail(await api.chatSessionDetail(sessionId, { limit: 50 }))
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    }
  }

  const columns: ColumnsType<ChatSessionItem> = [
    { title: '会话', dataIndex: 'title' },
    { title: '用户', render: (_, s) => s.user ? `${s.user.display_name}（${s.user.username}）` : '—' },
    { title: '状态', dataIndex: 'status', render: (s) => <Tag>{s === 'hidden' ? '已隐藏' : '活跃'}</Tag> },
    { title: '消息数', dataIndex: 'message_count' },
    { title: 'Token', render: (_, s) => s.token_usage.total_tokens },
    { title: '批次数', dataIndex: 'batch_count' },
    { title: '最后消息', dataIndex: 'last_message_at', render: (v) => formatDateTime(v) },
    { title: '操作', render: (_, s) => <Button size="small" onClick={() => void openDetail(s.session_id)}>查看</Button> },
  ]

  if (detail) {
    return (
      <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
        <Button style={{ marginBottom: 16 }} onClick={() => setDetail(null)}>返回列表</Button>
        <Card title={`${detail.session.title} · ${detail.session.user?.display_name ?? ''}`} size="small" style={{ marginBottom: 16 }}>
          <Space wrap>
            <Tag>消息 {detail.session.message_count}</Tag>
            <Tag>Token {detail.session.token_usage.total_tokens}</Tag>
            <Tag>批次 {detail.session.batch_count}</Tag>
          </Space>
        </Card>
        {detail.messages.map((m) => (
          <Card key={m.message_id} size="small" style={{ marginBottom: 12 }}>
            <Space wrap style={{ marginBottom: 8 }}>
              <Tag color={m.role === 'user' ? 'blue' : m.role === 'assistant' ? 'green' : 'default'}>{m.role}</Tag>
              {m.agent_name && <Tag>{m.agent_name}</Tag>}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{formatDateTime(m.created_at)}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>in {m.token_in} / out {m.token_out}</Typography.Text>
            </Space>
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
            {m.agent_runs.length > 0 && (
              <Collapse size="small" ghost style={{ marginTop: 8 }}
                items={[{ key: 'runs', label: `Agent 调用（${m.agent_runs.length}）`, children:
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {m.agent_runs.map((r) => (
                      <li key={r.run_id}>{r.agent_name} · {r.status} · {r.latency_ms ?? '-'}ms · {r.model_name ?? '—'}</li>
                    ))}
                  </ul>
                }]}
              />
            )}
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input placeholder="用户名/显示名" allowClear style={{ width: 180 }} onChange={(e) => setFilters((f) => ({ ...f, user_keyword: e.target.value }))} />
        <Input placeholder="会话标题" allowClear style={{ width: 180 }} onChange={(e) => setFilters((f) => ({ ...f, title_keyword: e.target.value }))} />
        <Select value={filters.status} style={{ width: 120 }} options={[{ value: 'all', label: '全部' }, { value: 'active', label: '活跃' }, { value: 'hidden', label: '已隐藏' }]} onChange={(v) => setFilters((f) => ({ ...f, status: v }))} />
        <Button type="primary" onClick={() => void load(1)}>查询</Button>
      </Space>
      <Table rowKey="session_id" columns={columns} dataSource={data?.items ?? []} loading={loading}
        pagination={{ current: page, pageSize: 20, total: data?.total ?? 0, onChange: (p) => void load(p), showSizeChanger: false }} />
    </div>
  )
}
