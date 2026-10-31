import { Button, Card, Empty, Pagination, Result, Skeleton } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import AuthedImage from '@/shared/components/AuthedImage'
import type { HistoryListResponse } from '@/shared/types'
import { formatDateTime } from '@/shared/utils/time'
import * as api from '../api'

/** 历史作品：只读列表（每页 20 条，页码写入 URL）。 */
export default function HistoryPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState<HistoryListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const page = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10) || 1)

  const load = useCallback(async (p: number) => {
    setLoading(true)
    setError(false)
    try {
      setData(await api.listHistory(p))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(page)
  }, [page, load])

  const onPageChange = (p: number) => {
    setSearchParams(p === 1 ? {} : { page: String(p) })
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Result
          status="warning"
          title="加载失败"
          extra={
            <Button type="primary" onClick={() => void load(page)}>
              点击重试
            </Button>
          }
        />
      </div>
    )
  }

  if (loading && !data) {
    return (
      <div style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    )
  }

  if (data && data.items.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Empty description="还没有作品，去创作台生成第一组图吧">
          <Button type="primary" onClick={() => navigate('/workspace')}>
            去创作
          </Button>
        </Empty>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: 16,
        }}
      >
        {(data?.items ?? []).map((item) => (
          <Card
            key={item.batch_id}
            hoverable
            cover={
              <AuthedImage
                src={item.cover_thumbnail_url}
                alt={item.product_name}
                className="img-fixed"
              />
            }
            styles={{ body: { padding: 12 } }}
            onClick={() => navigate(`/history/${item.batch_id}`)}
          >
            <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.product_name}
            </div>
            <div style={{ color: '#6b7280', fontSize: 12, marginTop: 4 }}>
              {item.main_count} 主图 + {item.detail_count} 详情图
            </div>
            <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>
              {item.success_count === item.total_count
                ? `${item.total_count} 张`
                : `${item.success_count}/${item.total_count} 张`}{' '}
              · {formatDateTime(item.created_at)}
            </div>
          </Card>
        ))}
      </div>

      {data && data.total > data.page_size && (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
          <Pagination
            current={page}
            pageSize={data.page_size}
            total={data.total}
            onChange={onPageChange}
            showSizeChanger={false}
          />
        </div>
      )}
    </div>
  )
}
