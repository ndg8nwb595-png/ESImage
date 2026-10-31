// 工作台全局状态：会话、消息、参数、上传、生成批次。
// 参数与上传图 ID 按 PRD §11.5.13 由前端 localStorage 保存，刷新/切换会话可恢复。

import { create } from 'zustand'

import type {
  BatchDetail,
  ChatMessage,
  FullBatch,
  SampleBatch,
  SessionItem,
  UploadAsset,
  WorkspaceParams,
} from '@/shared/types'
import * as api from './api'

const PARAMS_KEY = 'esimage_workspace_params'
const UPLOAD_IDS_KEY = 'esimage_workspace_upload_ids'

const DEFAULT_PARAMS: WorkspaceParams = {
  product_name: '',
  style_text: null,
  width: null,
  height: null,
  template_id: null,
}

function loadStoredParams(): WorkspaceParams {
  try {
    const raw = localStorage.getItem(PARAMS_KEY)
    if (!raw) return DEFAULT_PARAMS
    return { ...DEFAULT_PARAMS, ...(JSON.parse(raw) as Partial<WorkspaceParams>) }
  } catch {
    return DEFAULT_PARAMS
  }
}

function loadStoredUploadIds(): number[] {
  try {
    const raw = localStorage.getItem(UPLOAD_IDS_KEY)
    if (!raw) return []
    const ids = JSON.parse(raw) as unknown
    return Array.isArray(ids) ? ids.filter((n): n is number => Number.isInteger(n)) : []
  } catch {
    return []
  }
}

interface WorkspaceState {
  sessions: SessionItem[]
  currentSessionId: number | null
  messages: ChatMessage[]
  messagesLoading: boolean
  params: WorkspaceParams
  uploads: UploadAsset[]
  sampleBatch: SampleBatch | null
  activeBatch: BatchDetail | null
  fullBatch: FullBatch | null

  loadSessions: () => Promise<void>
  restoreUploads: () => Promise<void>
  openSession: (id: number) => Promise<void>
  newSession: () => void
  setCurrentSession: (id: number | null) => void
  setParams: (patch: Partial<WorkspaceParams>) => void
  setUploads: (uploads: UploadAsset[]) => void
  setMessages: (messages: ChatMessage[]) => void
  setSampleBatch: (batch: SampleBatch | null) => void
  setActiveBatch: (batch: BatchDetail | null) => void
  setFullBatch: (batch: FullBatch | null) => void
  clearGeneration: () => void
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  messagesLoading: false,
  params: loadStoredParams(),
  uploads: [],
  sampleBatch: null,
  activeBatch: null,
  fullBatch: null,

  loadSessions: async () => {
    try {
      const data = await api.listSessions()
      set({ sessions: data.items })
    } catch {
      // 会话列表加载失败不阻断工作台其余部分
    }
  },

  restoreUploads: async () => {
    const ids = loadStoredUploadIds()
    if (ids.length === 0) return
    const restored: UploadAsset[] = []
    for (const id of ids) {
      try {
        restored.push(await api.getUpload(id))
      } catch {
        // 已删除/失效的上传图跳过
      }
    }
    set({ uploads: restored })
  },

  openSession: async (id) => {
    set({
      currentSessionId: id,
      messagesLoading: true,
      messages: [],
      sampleBatch: null,
      activeBatch: null,
      fullBatch: null,
    })
    try {
      const data = await api.listMessages(id)
      set({ messages: data.items, messagesLoading: false })
    } catch {
      set({ messagesLoading: false })
    }
  },

  newSession: () =>
    set({
      currentSessionId: null,
      messages: [],
      sampleBatch: null,
      activeBatch: null,
      fullBatch: null,
    }),

  setCurrentSession: (id) => set({ currentSessionId: id }),

  setParams: (patch) => {
    const params = { ...get().params, ...patch }
    localStorage.setItem(PARAMS_KEY, JSON.stringify(params))
    set({ params })
  },

  setUploads: (uploads) => {
    localStorage.setItem(
      UPLOAD_IDS_KEY,
      JSON.stringify(uploads.map((u) => u.upload_id)),
    )
    set({ uploads })
  },

  setMessages: (messages) => set({ messages }),

  setSampleBatch: (batch) => set({ sampleBatch: batch }),
  setActiveBatch: (batch) => set({ activeBatch: batch }),
  setFullBatch: (batch) => set({ fullBatch: batch }),
  clearGeneration: () => set({ sampleBatch: null, activeBatch: null, fullBatch: null }),
}))
