// 创作工作台接口：会话、消息、上传、生成批次（2 号 PRD 最小 demo）。

import { request } from '@/shared/api/client'
import type {
  BatchDetail,
  FullBatch,
  MessageListResponse,
  SampleBatch,
  SessionListResponse,
  UploadAsset,
} from '@/shared/types'

export function listSessions(): Promise<SessionListResponse> {
  return request<SessionListResponse>('/sessions')
}

export function listMessages(sessionId: number, page = 1, pageSize = 100): Promise<MessageListResponse> {
  return request<MessageListResponse>(
    `/sessions/${sessionId}/messages?page=${page}&page_size=${pageSize}`,
  )
}

export function uploadImage(file: File): Promise<UploadAsset> {
  const form = new FormData()
  form.append('file', file)
  return request<UploadAsset>('/uploads', { method: 'POST', body: form })
}

export function getUpload(uploadId: number): Promise<UploadAsset> {
  return request<UploadAsset>(`/uploads/${uploadId}`)
}

export function removeUpload(uploadId: number): Promise<null> {
  return request<null>(`/uploads/${uploadId}`, { method: 'DELETE' })
}

export interface SamplePayload {
  client_request_id: string
  session_id: number | null
  product_name: string
  style_text: string | null
  width: number | null
  height: number | null
  template_id: number | null
  upload_ids: number[] | null
}

export function createSample(payload: SamplePayload): Promise<SampleBatch> {
  return request<SampleBatch>('/generations/sample', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getBatch(batchId: number): Promise<BatchDetail> {
  return request<BatchDetail>(`/generations/${batchId}`)
}

export function confirmBatch(batchId: number, clientRequestId: string): Promise<FullBatch> {
  return request<FullBatch>(`/generations/${batchId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ client_request_id: clientRequestId }),
  })
}
