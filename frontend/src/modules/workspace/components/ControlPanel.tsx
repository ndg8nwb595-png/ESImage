import { DeleteOutlined, UploadOutlined } from '@ant-design/icons'
import { App, Button, Input, Select, Space, Upload } from 'antd'
import { useState } from 'react'

import AuthedImage from '@/shared/components/AuthedImage'
import { useWorkspaceStore } from '../store'
import * as api from '../api'

const SIZE_OPTIONS = [
  { value: 'default', label: '1:1（默认 1000×1000）' },
  { value: '3:4', label: '3:4（750×1000）' },
  { value: '16:9', label: '16:9（1280×720）' },
]

function sizeValue(width: number | null, height: number | null): string {
  if (width === 750 && height === 1000) return '3:4'
  if (width === 1280 && height === 720) return '16:9'
  return 'default'
}

/** 右栏：参数面板 + 商品图上传。 */
export default function ControlPanel() {
  const { message } = App.useApp()
  const params = useWorkspaceStore((s) => s.params)
  const uploads = useWorkspaceStore((s) => s.uploads)
  const setParams = useWorkspaceStore((s) => s.setParams)
  const setUploads = useWorkspaceStore((s) => s.setUploads)
  const [uploading, setUploading] = useState(false)

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const asset = await api.uploadImage(file)
      setUploads([...useWorkspaceStore.getState().uploads, asset])
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const beforeUpload = (file: File) => {
    const name = file.name.toLowerCase()
    const okExt = /\.(jpe?g|png|webp)$/.test(name)
    const okMime = ['image/jpeg', 'image/png', 'image/webp'].includes(file.type)
    if (!okExt && !okMime) {
      message.error('仅支持 JPG、PNG、WEBP 格式')
      return Upload.LIST_IGNORE
    }
    if (file.size > 10 * 1024 * 1024) {
      message.error('单张图片不能超过 10MB')
      return Upload.LIST_IGNORE
    }
    if (uploads.length >= 5) {
      message.warning('最多上传 5 张商品图')
      return Upload.LIST_IGNORE
    }
    void handleUpload(file)
    return false
  }

  const handleRemove = async (uploadId: number) => {
    try {
      await api.removeUpload(uploadId)
      setUploads(useWorkspaceStore.getState().uploads.filter((u) => u.upload_id !== uploadId))
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  return (
    <>
      <div className="ws-right-section">
        <div className="ws-right-section-title">参数</div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4 }}>
            <span style={{ color: '#dc2626' }}>*</span> 商品名称
          </div>
          <Input
            value={params.product_name}
            maxLength={60}
            placeholder="必填，例如：无线蓝牙耳机"
            onChange={(e) => setParams({ product_name: e.target.value })}
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4 }}>风格（选填）</div>
          <Input
            value={params.style_text ?? ''}
            maxLength={50}
            placeholder="例如：简洁白底、高级质感"
            onChange={(e) => setParams({ style_text: e.target.value || null })}
          />
        </div>
        <div>
          <div style={{ marginBottom: 4 }}>尺寸（选填）</div>
          <Select
            style={{ width: '100%' }}
            value={sizeValue(params.width, params.height)}
            options={SIZE_OPTIONS}
            onChange={(value) => {
              if (value === '3:4') setParams({ width: 750, height: 1000 })
              else if (value === '16:9') setParams({ width: 1280, height: 720 })
              else setParams({ width: null, height: null })
            }}
          />
        </div>
      </div>

      <div className="ws-right-section">
        <div className="ws-right-section-title">
          商品图 <span style={{ color: '#6b7280', fontWeight: 400 }}>（选填，1~5 张）</span>
        </div>
        <Upload
          accept=".jpg,.jpeg,.png,.webp"
          multiple
          showUploadList={false}
          beforeUpload={beforeUpload}
        >
          <Button icon={<UploadOutlined />} loading={uploading} disabled={uploads.length >= 5}>
            上传商品图
          </Button>
        </Upload>

        {uploads.length > 0 && (
          <Space wrap style={{ marginTop: 12 }}>
            {uploads.map((u) => (
              <div key={u.upload_id} style={{ position: 'relative', width: 72, height: 72 }}>
                <AuthedImage
                  src={u.thumbnail_url}
                  alt={u.original_name}
                  className="img-fixed"
                />
                <Button
                  size="small"
                  danger
                  type="text"
                  icon={<DeleteOutlined />}
                  style={{ position: 'absolute', right: 0, top: 0 }}
                  onClick={() => void handleRemove(u.upload_id)}
                />
              </div>
            ))}
          </Space>
        )}
      </div>
    </>
  )
}
