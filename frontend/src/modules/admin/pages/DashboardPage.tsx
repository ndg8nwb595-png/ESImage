import { App, Button, Card, Col, DatePicker, Input, Row, Select, Space, Statistic, Table, Tabs } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import * as api from '../api'
import type { DashboardSummary, TokenStatsResponse } from '../api'

const AGENT_OPTIONS = [
  { value: 'planner', label: '规划 Agent' },
  { value: 'product_understanding', label: '商品理解 Agent' },
  { value: 'copywriter', label: '文案 Agent' },
  { value: 'prompt_builder', label: '提示词 Agent' },
  { value: 'image_generator', label: '生图执行 Agent' },
  { value: 'quality_reviewer', label: '质量审核 Agent' },
  { value: 'repairer', label: '修复 Agent' },
  { value: 'platform_rule', label: '平台规范 Agent' },
]

function formatNumber(n: number | undefined): string {
  return (n ?? 0).toLocaleString('zh-CN')
}

function OverviewTab() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(() => {
    setError(false)
    api
      .getDashboardSummary()
      .then(setSummary)
      .catch(() => {
        setError(true)
        message.error('加载失败，请重试')
      })
  }, [message])

  useEffect(() => {
    load()
  }, [load])

  if (error && !summary) {
    return (
      <Button type="primary" onClick={load}>
        加载失败，点击重试
      </Button>
    )
  }

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card>
          <Statistic title="用户总数" value={summary?.user_total ?? 0} />
        </Card>
      </Col>
      <Col span={6}>
        <Card hoverable onClick={() => navigate('/admin/content')}>
          <Statistic title="今日生成图片数" value={summary?.today_image_count ?? 0} />
        </Card>
      </Col>
      <Col span={6}>
        <Card hoverable onClick={() => navigate('/admin/content')}>
          <Statistic title="累计图片数" value={formatNumber(summary?.total_image_count)} />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic title="今日 Token" value={formatNumber(summary?.today_token_total)} />
        </Card>
      </Col>
    </Row>
  )
}

function TokenTab() {
  const { message } = App.useApp()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(6, 'day'), dayjs()])
  const [user, setUser] = useState('')
  const [agentCodes, setAgentCodes] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [data, setData] = useState<TokenStatsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)

  const load = useCallback(
    async (p = 1) => {
      setLoading(true)
      try {
        const res = await api.getTokenStats({
          start_date: range[0].format('YYYY-MM-DD'),
          end_date: range[1].format('YYYY-MM-DD'),
          user: user || undefined,
          agent_codes: agentCodes.join(',') || undefined,
          model: model || undefined,
          page: p,
        })
        setData(res)
        setPage(p)
      } catch (err) {
        message.error(err instanceof Error ? err.message : '加载失败，请重试')
      } finally {
        setLoading(false)
      }
    },
    [range, user, agentCodes, model, message],
  )

  useEffect(() => {
    void load(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const columns: ColumnsType<api.TokenStatsItem> = [
    { title: '日期', dataIndex: 'date', width: 110 },
    {
      title: '用户',
      key: 'user',
      render: (_, r) => r.display_name ?? r.username ?? '—',
    },
    { title: 'Agent', dataIndex: 'agent_name', width: 150 },
    { title: '模型', dataIndex: 'model_name', render: (v) => v ?? '—' },
    { title: '调用次数', dataIndex: 'call_count', width: 90, align: 'right' },
    { title: '输入 Token', dataIndex: 'prompt_tokens', width: 110, align: 'right' },
    { title: '输出 Token', dataIndex: 'completion_tokens', width: 110, align: 'right' },
    { title: '合计 Token', dataIndex: 'total_tokens', width: 110, align: 'right' },
  ]

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <DatePicker.RangePicker
          value={range}
          onChange={(v) => v && setRange([v[0]!, v[1]!])}
          allowClear={false}
        />
        <Input
          placeholder="用户名/显示名"
          value={user}
          onChange={(e) => setUser(e.target.value)}
          style={{ width: 160 }}
        />
        <Select
          mode="multiple"
          placeholder="Agent"
          value={agentCodes}
          onChange={setAgentCodes}
          options={AGENT_OPTIONS}
          style={{ minWidth: 200 }}
          allowClear
        />
        <Input
          placeholder="模型名"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          style={{ width: 160 }}
        />
        <Button type="primary" onClick={() => void load(1)} loading={loading}>
          查询
        </Button>
        <Button onClick={() => { setRange([dayjs().subtract(6, 'day'), dayjs()]); setUser(''); setAgentCodes([]); setModel('') }}>
          重置
        </Button>
      </Space>

      {data && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}><Statistic title="输入 Token" value={data.summary.prompt_tokens} /></Col>
          <Col span={6}><Statistic title="输出 Token" value={data.summary.completion_tokens} /></Col>
          <Col span={6}><Statistic title="合计 Token" value={data.summary.total_tokens} /></Col>
          <Col span={6}><Statistic title="调用次数" value={data.summary.call_count} /></Col>
        </Row>
      )}

      <Table
        rowKey={(r) => `${r.date}-${r.user_id}-${r.agent_code}-${r.model_name}`}
        columns={columns}
        dataSource={data?.items ?? []}
        loading={loading}
        pagination={{
          current: page,
          pageSize: data?.page_size ?? 20,
          total: data?.total ?? 0,
          onChange: (p) => void load(p),
          showSizeChanger: false,
        }}
        locale={{ emptyText: '暂无 Token 数据' }}
      />
    </div>
  )
}

export default function DashboardPage() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '概览', children: <OverviewTab /> },
          { key: 'tokens', label: 'Token 统计', children: <TokenTab /> },
        ]}
      />
    </div>
  )
}
