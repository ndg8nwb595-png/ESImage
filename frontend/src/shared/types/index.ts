// 共享类型：字段与后端接口文档/响应逐字对齐（snake_case）。

export interface User {
  id: number
  username: string
  display_name: string
  avatar_url: string | null
}

/** 登录响应中的 user：内嵌角色与权限（1 号文档约定）。 */
export interface LoginResponse {
  token: string
  expires_at: string
  user: User & { roles: string[]; permissions: string[] }
}

/** GET /auth/me 响应：顶层返回角色与权限（9 号文档约定）。 */
export interface MeResponse {
  user: User
  roles: string[]
  permissions: string[]
}

export interface SessionItem {
  session_id: number
  title: string
  status: string
  last_message_at: string | null
  last_message_preview: string | null
  latest_batch_id: number | null
  created_at: string
  updated_at: string
}

export interface SessionListResponse {
  items: SessionItem[]
  total: number
}

export interface ChatMessage {
  message_id: number
  session_id: number
  role: 'user' | 'assistant'
  agent_code: string | null
  content: string
  content_type: string
  status: string
  token_in: number | null
  token_out: number | null
  created_at: string
}

export interface MessageListResponse {
  items: ChatMessage[]
  total: number
  page: number
  page_size: number
}

export interface UploadAsset {
  upload_id: number
  file_url: string
  thumbnail_url: string
  width: number
  height: number
  size_bytes: number
  mime_type: string
  original_name: string
  sort_order: number
  status: string
  created_at: string
}

/** 参数面板快照，随请求提交。 */
export interface WorkspaceParams {
  product_name: string
  style_text: string | null
  width: number | null
  height: number | null
  template_id: number | null
}

export interface SampleBatch {
  batch_id: number
  session_id: number
  session_title: string | null
  batch_type: string
  status: string
  total_count: number
  completed_count: number
}

export interface GeneratedImage {
  image_id: number
  index: number
  image_role: 'main' | 'detail'
  status: string
  thumbnail_url: string | null
  content_url: string | null
  error_message: string | null
  width: number | null
  height: number | null
}

export interface BatchDetail {
  batch_id: number
  batch_type: string
  status: string
  stage: string | null
  total_count: number
  completed_count: number
  images: GeneratedImage[]
  error_message: string | null
  created_at: string
  finished_at: string | null
}

export interface FullBatch {
  full_batch_id: number
  total_count: number
  status: string
}

export interface HistoryItem {
  batch_id: number
  product_name: string
  main_count: number
  detail_count: number
  success_count: number
  total_count: number
  cover_image_id: number
  cover_thumbnail_url: string
  created_at: string
}

export interface HistoryListResponse {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

export interface HistoryImage {
  image_id: number
  index: number
  image_role: 'main' | 'detail'
  width: number | null
  height: number | null
  thumbnail_url: string
  content_url: string
  created_at: string
}

export interface HistoryDetail {
  batch_id: number
  product_name: string
  style_text: string | null
  width: number
  height: number
  main_count: number
  detail_count: number
  success_count: number
  total_count: number
  status: string
  created_at: string
  images: HistoryImage[]
}
