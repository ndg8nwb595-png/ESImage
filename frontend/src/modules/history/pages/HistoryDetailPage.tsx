import { DownloadOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { App, Button, Descriptions, Modal, Result, Skeleton, Space } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import AuthedImage from '@/shared/components/AuthedImage'
import { downloadAuthed } from '@/shared/utils/download'
import type { HistoryDetail, HistoryImage } from '@/shared/types'
import { formatDateTime } from '@/shared/utils/time'
import * as api from '../api'

/** 历史作品批次详情：图片网格、大图预览、单张与整组下载。 */
export default function HistoryDetailPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const { batchId } = useParams()
  const id = parseInt(batchId ?? '', 10)

  const [detail, setDetail] = useState<HistoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [downloadingZip, setDownloadingZip] = useState(false)

  useEffect(() => {
    if (!Number.isInteger(id)) {
      setError(true)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(false)
    api
      .getHistoryDetail(id)
      .then(setDetail)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [id])

  const downloadSingle = async (image: HistoryImage) => {
    try {
      await downloadAuthed(`/images/${image.image_id}/download`, `image_${image.index}.png`)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下载失败，请稍后重试')
    }
  }

  const downloadZip = async () => {
    if (!detail) return
    setDownloadingZip(true)
    try {
      await downloadAuthed(`/batches/${detail.batch_id}/download`, 'batch.zip')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下载失败，请稍后重试')
    } finally {
      setDownloadingZip(false)
    }
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Result
          status="404"
          title="批次不存在"
          extra={
            <Button type="primary" onClick={() => navigate('/history')}>
              返回历史列表
            </Button>
          }
        />
      </div>
    )
  }

  if (loading || !detail) {
    return (
      <div style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    )
  }

  const images = detail.images
  const previewImage = previewIndex !== null ? images[previewIndex] : null

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<LeftOutlined />} onClick={() => navigate('/history')}>
          返回
        </Button>
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          loading={downloadingZip}
          onClick={() => void downloadZip()}
        >
          下载整组（ZIP）
        </Button>
      </Space>

      <Descriptions column={2} size="small" bordered>
        <Descriptions.Item label="商品名称">{detail.product_name}</Descriptions.Item>
        <Descriptions.Item label="状态">
          {detail.status === 'completed' ? '已完成' : '部分失败'}
        </Descriptions.Item>
        <Descriptions.Item label="风格">{detail.style_text ?? '未填写'}</Descriptions.Item>
        <Descriptions.Item label="尺寸">
          {detail.width} × {detail.height}
        </Descriptions.Item>
        <Descriptions.Item label="张数">
          {detail.success_count}/{detail.total_count} 张（{detail.main_count} 主图 + {detail.detail_count} 详情图）
        </Descriptions.Item>
        <Descriptions.Item label="生成时间">{formatDateTime(detail.created_at)}</Descriptions.Item>
      </Descriptions>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: 12,
          marginTop: 16,
        }}
      >
        {images.map((img, idx) => (
          <div
            key={img.image_id}
            style={{ position: 'relative', border: '1px solid var(--color-border)', borderRadius: 6, overflow: 'hidden', cursor: 'pointer' }}
            onClick={() => setPreviewIndex(idx)}
          >
            <AuthedImage src={img.thumbnail_url} alt={`${img.image_role}${img.index}`} className="img-fixed" />
            <span
              style={{
                position: 'absolute', left: 6, top: 6, background: 'rgba(15,23,42,0.75)', color: '#fff', fontSize: 12, padding: '1px 8px', borderRadius: 10,
              }}
            >
              {img.image_role === 'main' ? '主图' : '详情'}
              {img.index}
            </span>
          </div>
        ))}
      </div>

      <Modal
        open={previewImage !== null}
        footer={null}
        onCancel={() => setPreviewIndex(null)}
        width={760}
        title={
          previewImage
            ? `${previewImage.image_role === 'main' ? '主图' : '详情图'} ${previewImage.index}（${previewImage.width ?? '-'}×${previewImage.height ?? '-'}）`
            : ''
        }
      >
        {previewImage && (
          <>
            <div style={{ textAlign: 'center' }}>
              <AuthedImage src={previewImage.content_url} alt="预览" className="img-preview" />
            </div>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 16 }}>
              <Button
                icon={<LeftOutlined />}
                disabled={previewIndex === 0}
                onClick={() => setPreviewIndex((p) => (p === null ? p : p - 1))}
              >
                上一张
              </Button>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={() => void downloadSingle(previewImage)}
              >
                下载这张
              </Button>
              <Button
                icon={<RightOutlined />}
                disabled={previewIndex === images.length - 1}
                onClick={() => setPreviewIndex((p) => (p === null ? p : p + 1))}
              >
                下一张
              </Button>
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}
