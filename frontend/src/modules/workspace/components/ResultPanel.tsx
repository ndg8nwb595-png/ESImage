import { DownloadOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { App, Button, Modal, Space, Spin } from 'antd'
import { useEffect, useState } from 'react'

import { ApiError } from '@/shared/api/client'
import AuthedImage from '@/shared/components/AuthedImage'
import { downloadAuthed } from '@/shared/utils/download'
import type { GeneratedImage } from '@/shared/types'
import * as api from '../api'
import { useWorkspaceStore } from '../store'

const SAMPLE_TERMINAL = ['sample_ready', 'failed', 'cancelled']
const FULL_TERMINAL = ['completed', 'partially_failed', 'failed', 'cancelled']

/** 右栏：生成动作、示例图确认与全套结果网格。 */
export default function ResultPanel() {
  const { message } = App.useApp()
  const params = useWorkspaceStore((s) => s.params)
  const uploads = useWorkspaceStore((s) => s.uploads)
  const currentSessionId = useWorkspaceStore((s) => s.currentSessionId)
  const activeBatch = useWorkspaceStore((s) => s.activeBatch)

  const [polling, setPolling] = useState<{ id: number; type: 'sample' | 'full' } | null>(null)
  const [starting, setStarting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [preview, setPreview] = useState<GeneratedImage | null>(null)

  // 批次状态轮询：示例图出图 / 全套完成即停止。
  useEffect(() => {
    if (!polling) return
    const terminal = polling.type === 'sample' ? SAMPLE_TERMINAL : FULL_TERMINAL
    let cancelled = false
    const tick = async () => {
      try {
        const detail = await api.getBatch(polling.id)
        if (cancelled) return
        useWorkspaceStore.getState().setActiveBatch(detail)
        if (terminal.includes(detail.status)) setPolling(null)
      } catch {
        // 轮询失败不中断，下一轮重试
      }
    }
    void tick()
    const timer = setInterval(() => void tick(), 1200)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [polling])

  const startSample = async () => {
    if (!params.product_name.trim()) {
      message.warning('请先填写商品名称')
      return
    }
    setStarting(true)
    try {
      const batch = await api.createSample({
        client_request_id: crypto.randomUUID(),
        session_id: currentSessionId,
        product_name: params.product_name.trim(),
        style_text: params.style_text,
        width: params.width,
        height: params.height,
        template_id: params.template_id,
        upload_ids: uploads.length > 0 ? uploads.map((u) => u.upload_id) : null,
      })
      const store = useWorkspaceStore.getState()
      store.setSampleBatch(batch)
      store.setFullBatch(null)
      if (batch.session_id) {
        store.setCurrentSession(batch.session_id)
        void store.loadSessions()
      }
      setPolling({ id: batch.batch_id, type: 'sample' })
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '生成失败，请重试')
    } finally {
      setStarting(false)
    }
  }

  const confirmSample = async () => {
    if (!activeBatch) return
    setConfirming(true)
    try {
      const full = await api.confirmBatch(activeBatch.batch_id, crypto.randomUUID())
      useWorkspaceStore.getState().setFullBatch(full)
      setPolling({ id: full.full_batch_id, type: 'full' })
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '确认失败，请重试')
    } finally {
      setConfirming(false)
    }
  }

  const download = async (image: GeneratedImage) => {
    try {
      await downloadAuthed(`/images/${image.image_id}/download`, `image_${image.index}.png`)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下载失败')
    }
  }

  const batch = activeBatch
  const isSampleReady = batch?.batch_type === 'sample' && batch.status === 'sample_ready'
  const sampleImage = isSampleReady ? batch.images.find((i) => i.status === 'success') : null
  const isFullDone =
    batch?.batch_type === 'full' && (batch.status === 'completed' || batch.status === 'partially_failed')
  const processing = batch ? ['queued', 'running'].includes(batch.status) : false

  return (
    <>
      <div className="ws-right-section">
        <div className="ws-right-section-title">生成</div>
        <Button
          type="primary"
          block
          icon={<ThunderboltOutlined />}
          loading={starting}
          disabled={confirming || processing}
          onClick={() => void startSample()}
        >
          生成示例图
        </Button>
        {!params.product_name.trim() && (
          <div style={{ color: '#6b7280', fontSize: 12, marginTop: 6 }}>需先填写商品名称</div>
        )}
      </div>

      {processing && (
        <div className="ws-right-section">
          <Space>
            <Spin size="small" />
            <span>{batch!.stage ?? '生成中…'}</span>
          </Space>
        </div>
      )}

      {batch && batch.status === 'failed' && (
        <div className="ws-right-section">
          <div style={{ color: '#dc2626' }}>生成失败：{batch.error_message ?? '请重试'}</div>
        </div>
      )}

      {isSampleReady && sampleImage && (
        <div className="ws-right-section">
          <div className="ws-right-section-title">示例图（主图）</div>
          <div onClick={() => setPreview(sampleImage)} style={{ cursor: 'pointer' }}>
            <AuthedImage
              src={sampleImage.thumbnail_url ?? sampleImage.content_url}
              alt="示例图"
              className="img-fixed"
            />
          </div>
          <Space style={{ marginTop: 12 }} wrap>
            <Button icon={<ReloadOutlined />} loading={starting} onClick={() => void startSample()}>
              重新生成示例
            </Button>
            <Button type="primary" loading={confirming} onClick={() => void confirmSample()}>
              确认并生成全套
            </Button>
          </Space>
        </div>
      )}

      {isFullDone && batch && (
        <div className="ws-right-section">
          <div className="ws-right-section-title">
            结果（{batch.completed_count}/{batch.total_count}）
          </div>
          <div className="result-grid">
            {batch.images.map((img) => (
              <div key={img.image_id} className="result-cell" onClick={() => setPreview(img)}>
                <AuthedImage src={img.thumbnail_url} alt={`${img.image_role}${img.index}`} />
                <span className="result-badge">
                  {img.image_role === 'main' ? '主图' : '详情'}
                  {img.index}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Modal
        open={!!preview}
        footer={null}
        title={preview ? `${preview.image_role === 'main' ? '主图' : '详情图'} ${preview.index}` : ''}
        onCancel={() => setPreview(null)}
        width={640}
      >
        {preview && <AuthedImage src={preview.content_url} alt="预览" className="img-fixed" />}
        {preview && (
          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <Button type="primary" icon={<DownloadOutlined />} onClick={() => void download(preview)}>
              下载
            </Button>
          </div>
        )}
      </Modal>
    </>
  )
}
