import { App, Button, Form, Input, InputNumber, Modal, Space, Switch, Table, Tabs, Tag, Upload } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'

import * as api from '../assets/api'
import type { Material, SizePreset, Template } from '../assets/api'

function useList<T>(loadFn: () => Promise<{ items: T[] }>) {
  const { message } = App.useApp()
  const [items, setItems] = useState<T[]>([])
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    setLoading(true)
    try {
      setItems((await loadFn()).items)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [loadFn, message])
  useEffect(() => { void load() }, [load])
  return { items, loading, load }
}

function TemplateTab() {
  const { message } = App.useApp()
  const { items, loading, load } = useList(api.listTemplates)
  const [editing, setEditing] = useState<Template | null>(null)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const open = (t: Template | null) => {
    setEditing(t)
    setCreating(t === null)
    form.resetFields()
    if (t) form.setFieldsValue(t)
    else form.setFieldsValue({ sort_order: 0 })
  }

  const submit = async () => {
    const v = await form.validateFields()
    try {
      if (creating) await api.createTemplate(v)
      else await api.updateTemplate(editing!.id, v)
      message.success('已保存')
      setEditing(null); setCreating(false)
      void load()
    } catch (e) { if (e instanceof Error) message.error(e.message) }
  }

  const columns: ColumnsType<Template> = [
    { title: '名称', dataIndex: 'name' },
    { title: '风格文案', dataIndex: 'style_text', render: (v) => v ?? '—' },
    { title: '排序', dataIndex: 'sort_order' },
    {
      title: '状态', dataIndex: 'status',
      render: (s, r) => (
        <Switch checked={s === 'active'} onChange={async (on) => { try { await api.setTemplateStatus(r.id, on ? 'active' : 'disabled'); void load() } catch (e) { if (e instanceof Error) message.error(e.message) } }} />
      ),
    },
    { title: '操作', render: (_, r) => <Button size="small" onClick={() => open(r)}>编辑</Button> },
  ]

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => open(null)}>新建模板</Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} pagination={false} />
      <Modal title={creating ? '新建模板' : '编辑模板'} open={creating || editing !== null} onOk={() => void submit()} onCancel={() => { setEditing(null); setCreating(false) }} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}><Input maxLength={50} /></Form.Item>
          <Form.Item label="风格文案" name="style_text"><Input maxLength={50} /></Form.Item>
          <Form.Item label="提示词模板" name="prompt_template"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item label="版式参考" name="layout_ref"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="排序" name="sort_order"><InputNumber min={0} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function MaterialTab() {
  const { message } = App.useApp()
  const { items, loading, load } = useList(api.listMaterials)
  const [editing, setEditing] = useState<Material | null>(null)
  const [form] = Form.useForm()

  const open = (m: Material) => {
    setEditing(m)
    form.resetFields()
    form.setFieldsValue({ ...m, tags: m.tags?.join(',') ?? '' })
  }

  const submit = async () => {
    const v = await form.validateFields()
    try {
      await api.updateMaterial(editing!.id, { name: v.name, tags: v.tags ? String(v.tags).split(',').map((s: string) => s.trim()).filter(Boolean) : null })
      message.success('已保存')
      setEditing(null)
      void load()
    } catch (e) { if (e instanceof Error) message.error(e.message) }
  }

  const columns: ColumnsType<Material> = [
    { title: '名称', dataIndex: 'name' },
    { title: '标签', dataIndex: 'tags', render: (t: string[] | null) => (t ?? []).map((x) => <Tag key={x}>{x}</Tag>) },
    {
      title: '状态', dataIndex: 'status',
      render: (s, r) => (
        <Switch checked={s === 'active'} onChange={async (on) => { try { await api.setMaterialStatus(r.id, on ? 'active' : 'disabled'); void load() } catch (e) { if (e instanceof Error) message.error(e.message) } }} />
      ),
    },
    { title: '操作', render: (_, r) => <Button size="small" onClick={() => open(r)}>编辑</Button> },
  ]

  return (
    <div>
      <Upload showUploadList={false} accept=".jpg,.jpeg,.png,.webp" beforeUpload={(file) => {
        void api.uploadMaterial(file, file.name).then(() => { message.success('已上传'); void load() }).catch((e) => message.error(e instanceof Error ? e.message : '上传失败'))
        return false
      }}>
        <Button style={{ marginBottom: 16 }}>上传素材</Button>
      </Upload>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} pagination={false} />
      <Modal title="编辑素材" open={editing !== null} onOk={() => void submit()} onCancel={() => setEditing(null)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}><Input maxLength={50} /></Form.Item>
          <Form.Item label="标签（逗号分隔）" name="tags"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function SizeTab() {
  const { message } = App.useApp()
  const { items, loading, load } = useList(api.listSizes)
  const [editing, setEditing] = useState<SizePreset | null>(null)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const open = (s: SizePreset | null) => {
    setEditing(s); setCreating(s === null)
    form.resetFields()
    if (s) form.setFieldsValue(s)
    else form.setFieldsValue({ sort_order: 0 })
  }

  const submit = async () => {
    const v = await form.validateFields()
    try {
      if (creating) await api.createSize(v)
      else await api.updateSize(editing!.id, v)
      message.success('已保存')
      setEditing(null); setCreating(false)
      void load()
    } catch (e) { if (e instanceof Error) message.error(e.message) }
  }

  const columns: ColumnsType<SizePreset> = [
    { title: '平台', dataIndex: 'platform_name' },
    { title: '宽', dataIndex: 'width' },
    { title: '高', dataIndex: 'height' },
    { title: '排序', dataIndex: 'sort_order' },
    { title: '状态', dataIndex: 'status', render: (s) => <Tag color={s === 'active' ? 'green' : 'default'}>{s === 'active' ? '启用' : '停用'}</Tag> },
    { title: '操作', render: (_, r) => <Button size="small" onClick={() => open(r)}>编辑</Button> },
  ]

  return (
    <div>
      <Button type="primary" style={{ marginBottom: 16 }} onClick={() => open(null)}>新增尺寸</Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} pagination={false} />
      <Modal title={creating ? '新增尺寸' : '编辑尺寸'} open={creating || editing !== null} onOk={() => void submit()} onCancel={() => { setEditing(null); setCreating(false) }} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item label="平台名称" name="platform_name" rules={[{ required: true, message: '请输入平台名称' }]}><Input maxLength={50} /></Form.Item>
          <Space>
            <Form.Item label="宽" name="width" rules={[{ required: true, message: '请输入宽' }]}><InputNumber min={1} /></Form.Item>
            <Form.Item label="高" name="height" rules={[{ required: true, message: '请输入高' }]}><InputNumber min={1} /></Form.Item>
          </Space>
          <Form.Item label="排序" name="sort_order"><InputNumber min={0} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default function AssetsPage() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Tabs items={[
        { key: 'templates', label: '模板', children: <TemplateTab /> },
        { key: 'materials', label: '素材库', children: <MaterialTab /> },
        { key: 'sizes', label: '尺寸预设', children: <SizeTab /> },
      ]} />
    </div>
  )
}
