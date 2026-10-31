import { App, Button, Card, Form, Input, InputNumber, Modal, Space, Table, Tabs, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'

import { useAuthStore } from '@/shared/store/authStore'
import { formatDateTime } from '@/shared/utils/time'
import * as api from '../prompts/api'
import type { PromptDetail, PromptListItem } from '../prompts/api'

function ModelConfigTab() {
  const { message } = App.useApp()
  const permissions = useAuthStore((s) => s.permissions)
  const editable = permissions.includes('admin.model.edit')
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getModelConfig().then((c) => { if (c) form.setFieldsValue(c) }).catch(() => message.error('加载失败'))
  }, [form, message])

  const save = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try {
      await api.saveModelConfig(v)
      message.success('已保存')
    } catch (e) {
      if (e instanceof Error) message.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="模型配置" extra={editable ? <Button type="primary" loading={saving} onClick={() => void save()}>保存</Button> : null}>
      <Form form={form} layout="vertical" disabled={!editable}>
        <Form.Item label="服务商" name="provider"><Input /></Form.Item>
        <Form.Item label="API 地址" name="base_url" rules={[{ required: true, message: '请输入 API 地址' }]}><Input /></Form.Item>
        <Form.Item label="API Key" name="api_key" extra="留空表示不修改">
          <Input.Password placeholder={editable ? '输入新 Key 覆盖' : '******'} />
        </Form.Item>
        <Form.Item label="文本模型" name="text_model" rules={[{ required: true, message: '请输入文本模型名' }]}><Input /></Form.Item>
        <Form.Item label="图像模型" name="image_model" rules={[{ required: true, message: '请输入图像模型名' }]}><Input /></Form.Item>
        <Form.Item label="视觉模型" name="vision_model"><Input /></Form.Item>
        <Space wrap>
          <Form.Item label="温度" name="temperature"><InputNumber min={0} max={2} step={0.1} /></Form.Item>
          <Form.Item label="超时(秒)" name="timeout_seconds"><InputNumber min={30} max={300} /></Form.Item>
          <Form.Item label="并发" name="concurrency"><InputNumber min={1} max={16} /></Form.Item>
          <Form.Item label="重试次数" name="retry_count"><InputNumber min={0} max={3} /></Form.Item>
          <Form.Item label="上下文上限" name="max_context_tokens"><InputNumber min={0} /></Form.Item>
        </Space>
      </Form>
    </Card>
  )
}

function PromptsTab() {
  const { message } = App.useApp()
  const permissions = useAuthStore((s) => s.permissions)
  const editable = permissions.includes('admin.prompts.edit')
  const [items, setItems] = useState<PromptListItem[]>([])
  const [detail, setDetail] = useState<PromptDetail | null>(null)
  const [content, setContent] = useState('')

  useEffect(() => {
    api.listPrompts().then((r) => setItems(r.items)).catch(() => message.error('加载失败'))
  }, [message])

  const open = async (agentCode: string) => {
    try {
      const d = await api.getPrompt(agentCode)
      setDetail(d)
      setContent(d.content)
    } catch (e) {
      if (e instanceof Error) message.error(e.message)
    }
  }

  const save = async () => {
    if (!detail) return
    try {
      await api.savePrompt(detail.agent_code, content)
      message.success('已保存新版本')
      void open(detail.agent_code)
    } catch (e) {
      if (e instanceof Error) message.error(e.message)
    }
  }

  const rollback = async (version: number) => {
    if (!detail) return
    try {
      await api.activatePromptVersion(detail.agent_code, version)
      message.success('已回滚')
      void open(detail.agent_code)
    } catch (e) {
      if (e instanceof Error) message.error(e.message)
    }
  }

  const columns: ColumnsType<PromptListItem> = [
    { title: 'Agent', dataIndex: 'name' },
    { title: '标识', dataIndex: 'agent_code' },
    { title: '当前版本', dataIndex: 'current_version', render: (v) => <Tag>v{v}</Tag> },
    { title: '更新时间', dataIndex: 'updated_at', render: (v) => formatDateTime(v) },
    { title: '操作', render: (_, r) => <Button size="small" onClick={() => void open(r.agent_code)}>查看/编辑</Button> },
  ]

  return (
    <div>
      <Table rowKey="agent_code" columns={columns} dataSource={items} pagination={false} />
      <Modal
        open={detail !== null}
        onCancel={() => setDetail(null)}
        footer={editable ? [
          <Button key="save" type="primary" onClick={() => void save()}>保存新版本</Button>,
        ] : null}
        width={720}
        title={detail ? `${detail.name}（${detail.agent_code}）· 当前 v${detail.current_version}` : ''}
      >
        {detail && (
          <>
            <Input.TextArea value={content} onChange={(e) => setContent(e.target.value)} rows={10} disabled={!editable} />
            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>版本历史</div>
              {detail.versions.map((v) => (
                <div key={v.version} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--color-border)' }}>
                  <span>v{v.version} · {formatDateTime(v.created_at)}</span>
                  {editable && v.version !== detail.current_version && (
                    <Button size="small" onClick={() => void rollback(v.version)}>回滚到此版本</Button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}

export default function AgentConfigPage() {
  const permissions = useAuthStore((s) => s.permissions)
  const canModel = permissions.includes('admin.model.view')
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Tabs items={[
        ...(canModel ? [{ key: 'model', label: '模型配置', children: <ModelConfigTab /> }] : []),
        { key: 'prompts', label: '系统提示词', children: <PromptsTab /> },
      ]} />
    </div>
  )
}
