// 历史作品接口（5 号 PRD 最小 demo）。

import { request } from '@/shared/api/client'
import type { HistoryDetail, HistoryListResponse } from '@/shared/types'

export function listHistory(page = 1): Promise<HistoryListResponse> {
  return request<HistoryListResponse>(`/history?page=${page}`)
}

export function getHistoryDetail(batchId: number): Promise<HistoryDetail> {
  return request<HistoryDetail>(`/history/${batchId}`)
}
