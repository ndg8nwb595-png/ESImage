import { App, Breadcrumb, Button, Descriptions, Drawer, Input, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'

import AuthedImage from '@/shared/components/AuthedImage'
import { downloadAuthed } from '@/shared/utils/download'
import { formatDateTime } from '@/shared/utils/time'
import * as api from '../content/api'
import type { ContentBatch, ContentSession, ContentUser, ImageDetail } from '../content/api'

const STATUS_LABEL: Record<string, string> = {
  active: '正常', disabled: '禁用', deleted: '已删除',
  hidden: '已隐藏', completed: '已完成', partially_failed: '部分失败', failed: '失败',
  sample_ready: '待确认', confirmed: '已确认', success: '成功', cancelled: '已取消',
  queued: '排队中', running: '生成中', generating: '生成中', pending: '待处理', superseded: '被替代',
}

/** 内容追溯：用户 → 会话 → 批次 → 图片 三层钻取。 */
export default function ContentPage() {
  const { message } = App.useApp()
  const [user, setUser] = useState<ContentUser | null>(null)
  const [session, setSession] = useState<ContentSession | null>(null)
  const [batch, setBatch] = useState<ContentBatch | null>(null)
  const [detail, setDetail] = useState<ImageDetail | null>(null)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <a onClick={() => { setUser(null); setSession(null); setBatch(null) }}>生图记录</a> },
          ...(user ? [{ title: <a onClick={() => { setSession(null); setBatch(null) }}>{user.username}</a> }] : []),
          ...(session ? [{ title: <a onClick={() => setBatch(null)}>{session.title}</a> }] : []),
          ...(batch ? [{ title: batch.product_name }] : []),
        ]}
      />
      {!user && <UserLevel onPick={setUser} />}
      {user && !session && <SessionLevel user={user} onPick={setSession} onBack={() => setUser(null)} />}
      {session && !batch && <BatchLevel session={session} onPick={setBatch} onBack={() => setSession(null)} />}
      {batch && <ImageLevel batch={batch} onDetail={setDetail} onBack={() => setBatch(null)} />}

      <Drawer
        open={detail !== null}
        onClose={() => setDetail(null)}
        width={640}
        title={detail ? `${detail.product_name ?? ''} · ${detail.image_role === 'main' ? '主图' : '详情图'} ${detail.index_no}` : ''}
      >
        {detail && (
          <>
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <AuthedImage src={detail.preview_url} alt="预览" className="img-preview" />
            </div>
            {detail.download_url && (
              <Button
                type="primary"
                block
                onClick={() => void downloadAuthed(detail.download_url!.replace('/api/v1', ''), 'image.png').catch((e) => message.error(e.message))}
              >
                下载原图
              </Button>
            )}
            <Descriptions column={1} size="small" bordered style={{ marginTop: 16 }}>
              <Descriptions.Item label="状态">{STATUS_LABEL[detail.status] ?? detail.status}</Descriptions.Item>
              <Descriptions.Item label="批次">#{detail.batch_id}（{STATUS_LABEL[detail.batch_status ?? ''] ?? detail.batch_status}）</Descriptions.Item>
              <Descriptions.Item label="尺寸">{detail.width ?? '-'} × {detail.height ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="模型">{detail.model_name ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="耗时">{detail.latency_ms != null ? `${detail.latency_ms}ms` : '—'}</Descriptions.Item>
              <Descriptions.Item label="Token">{detail.prompt_tokens} / {detail.completion_tokens}</Descriptions.Item>
              <Descriptions.Item label="提示词">{detail.prompt ?? '—'}</Descriptions.Item>
              {detail.error_message && <Descriptions.Item label="失败原因">{detail.error_message}</Descriptions.Item>}
            </Descriptions>
          </>
        )}
      </Drawer>
    </div>
  )
}

function UserLevel({ onPick }: { onPick: (u: ContentUser) => void }) {
  const { message } = App.useApp()
  const [data, setData] = useState<api.Paged<ContentUser> | null>(null)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')

  const load = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      setData(await api.contentUsers({ keyword, page: p }))
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, message])

  useEffect(() => { void load(1) }, [load])

  const columns: ColumnsType<ContentUser> = [
    { title: '用户名', dataIndex: 'username' },
    { title: '显示名', dataIndex: 'display_name' },
    { title: '状态', dataIndex: 'status', render: (s) => <Tag>{STATUS_LABEL[s] ?? s}</Tag> },
    { title: '生成批次数', dataIndex: 'batch_count' },
    { title: '最近生成', dataIndex: 'last_generated_at', render: (v) => formatDateTime(v) },
    { title: '操作', render: (_, u) => <Button size="small" onClick={() => onPick(u)}>查看会话</Button> },
  ]

  return (
    <div>
      <Input.Search placeholder="用户名/显示名" style={{ width: 260, marginBottom: 16 }} onSearch={setKeyword} allowClear />
      <Table rowKey="user_id" columns={columns} dataSource={data?.items ?? []} loading={loading}
        pagination={{ total: data?.total ?? 0, pageSize: 20, onChange: (p) => void load(p), showSizeChanger: false }} />
    </div>
  )
}

function SessionLevel({ user, onPick, onBack }: { user: ContentUser; onPick: (s: ContentSession) => void; onBack: () => void }) {
  const { message } = App.useApp()
  const [data, setData] = useState<api.Paged<ContentSession> | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await api.contentSessions(user.user_id)) } catch (e) { message.error(e instanceof Error ? e.message : '加载失败') } finally { setLoading(false) }
  }, [user.user_id, message])
  useEffect(() => { void load() }, [load])

  const columns: ColumnsType<ContentSession> = [
    { title: '标题', dataIndex: 'title' },
    { title: '状态', dataIndex: 'status', render: (s) => <Tag>{STATUS_LABEL[s] ?? s}</Tag> },
    { title: '批次数', dataIndex: 'batch_count' },
    { title: '最后消息', dataIndex: 'last_message_at', render: (v) => formatDateTime(v) },
    { title: '操作', render: (_, s) => <Button size="small" onClick={() => onPick(s)}>查看批次</Button> },
  ]

  return (
    <div>
      <Button size="small" style={{ marginBottom: 16 }} onClick={onBack}>返回</Button>
      <Table rowKey="session_id" columns={columns} dataSource={data?.items ?? []} loading={loading} pagination={false} />
    </div>
  )
}

function BatchLevel({ session, onPick, onBack }: { session: ContentSession; onPick: (b: ContentBatch) => void; onBack: () => void }) {
  const { message } = App.useApp()
  const [data, setData] = useState<api.Paged<ContentBatch> | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await api.contentBatches(session.session_id)) } catch (e) { message.error(e instanceof Error ? e.message : '加载失败') } finally { setLoading(false) }
  }, [session.session_id, message])
  useEffect(() => { void load() }, [load])

  const columns: ColumnsType<ContentBatch> = [
    { title: '批次', dataIndex: 'batch_id' },
    { title: '类型', dataIndex: 'batch_type', render: (t) => (t === 'sample' ? '示例' : '全套') },
    { title: '商品名称', dataIndex: 'product_name' },
    { title: '状态', dataIndex: 'status', render: (s) => <Tag>{STATUS_LABEL[s] ?? s}</Tag> },
    { title: '进度', render: (_, b) => `${b.completed_count}/${b.total_count}` },
    { title: '创建时间', dataIndex: 'created_at', render: (v) => formatDateTime(v) },
    { title: '操作', render: (_, b) => <Button size="small" onClick={() => onPick(b)}>查看图片</Button> },
  ]

  return (
    <div>
      <Button size="small" style={{ marginBottom: 16 }} onClick={onBack}>返回</Button>
      <Table rowKey="batch_id" columns={columns} dataSource={data?.items ?? []} loading={loading} pagination={false} />
    </div>
  )
}

function ImageLevel({ batch, onDetail, onBack }: { batch: ContentBatch; onDetail: (d: ImageDetail) => void; onBack: () => void }) {
  const { message } = App.useApp()
  const [data, setData] = useState<api.Paged<api.ContentImage> | null>(null)
  const load = useCallback(async () => {
    try { setData(await api.contentImages(batch.batch_id)) } catch (e) { message.error(e instanceof Error ? e.message : '加载失败') }
  }, [batch.batch_id, message])
  useEffect(() => { void load() }, [load])

  const openDetail = async (imageId: number) => {
    try { onDetail(await api.imageDetail(imageId)) } catch (e) { message.error(e instanceof Error ? e.message : '加载失败') }
  }

  return (
    <div>
      <Button size="small" style={{ marginBottom: 16 }} onClick={onBack}>返回</Button>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 }}>
        {(data?.items ?? []).map((img) => (
          <div key={`${img.image_id}-${img.attempt_no}`} style={{ border: '1px solid var(--color-border)', borderRadius: 6, overflow: 'hidden', cursor: 'pointer' }} onClick={() => void openDetail(img.image_id)}>
            {img.thumbnail_url ? <AuthedImage src={img.thumbnail_url} alt={`${img.image_role}${img.index_no}`} className="img-fixed" /> : <div className="img-fixed" />}
            <div style={{ padding: 6, fontSize: 12 }}>
              <Space size={4}>
                <Tag>{img.image_role === 'main' ? '主图' : '详情'}{img.index_no}</Tag>
                <Tag>{STATUS_LABEL[img.status] ?? img.status}</Tag>
              </Space>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
