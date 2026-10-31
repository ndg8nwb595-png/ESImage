import { App, Button, Descriptions, Drawer, Input, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'

import { formatDateTime } from '@/shared/utils/time'
import * as api from '../audit/api'
import type { AuditLog } from '../audit/api'

/** 操作日志（仅超管）。 */
export default function AuditLogsPage() {
  const { message } = App.useApp()
  const [data, setData] = useState<api.AuditLogList | null>(null)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ keyword: '', result: '' })
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<AuditLog | null>(null)

  const load = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      setData(await api.listAuditLogs({ ...filters, page: p, page_size: 20 }))
      setPage(p)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [filters, message])

  useEffect(() => { void load(1) }, [load])

  const columns: ColumnsType<AuditLog> = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '操作人', dataIndex: 'username_snapshot', render: (v) => v ?? '—' },
    { title: '动作', dataIndex: 'action' },
    { title: '对象', render: (_, r) => r.target_type ? `${r.target_type}:${r.target_id}` : '—' },
    { title: '结果', dataIndex: 'result', render: (r) => <Tag color={r === 'success' ? 'green' : 'red'}>{r}</Tag> },
    { title: 'IP', dataIndex: 'ip', render: (v) => v ?? '—' },
    { title: '时间', dataIndex: 'created_at', render: (v) => formatDateTime(v) },
    { title: '操作', render: (_, r) => <Button size="small" onClick={() => setDetail(r)}>详情</Button> },
  ]

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input placeholder="操作人/动作" allowClear style={{ width: 200 }} onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))} />
        <Select placeholder="结果" allowClear style={{ width: 120 }} options={[{ value: 'success', label: '成功' }, { value: 'failed', label: '失败' }]} onChange={(v) => setFilters((f) => ({ ...f, result: v ?? '' }))} />
        <Button type="primary" onClick={() => void load(1)}>查询</Button>
      </Space>
      <Table rowKey="id" columns={columns} dataSource={data?.items ?? []} loading={loading}
        pagination={{ current: page, pageSize: 20, total: data?.total ?? 0, onChange: (p) => void load(p), showSizeChanger: false }} />

      <Drawer open={detail !== null} onClose={() => setDetail(null)} width={560} title={`日志 #${detail?.id ?? ''}`}>
        {detail && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="操作人">{detail.username_snapshot ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="动作">{detail.action}</Descriptions.Item>
            <Descriptions.Item label="结果">{detail.result}</Descriptions.Item>
            <Descriptions.Item label="对象">{detail.target_type ? `${detail.target_type}:${detail.target_id}` : '—'}</Descriptions.Item>
            <Descriptions.Item label="IP">{detail.ip ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="时间">{formatDateTime(detail.created_at)}</Descriptions.Item>
            <Descriptions.Item label="UA">{detail.user_agent ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="详情">{detail.detail ? JSON.stringify(detail.detail) : '—'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  )
}
