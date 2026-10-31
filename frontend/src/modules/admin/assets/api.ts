// 素材与模板接口（9 号 §6.6）。

import { request } from '@/shared/api/client'

export interface Template {
  id: number
  name: string
  style_text: string | null
  thumbnail_path: string | null
  prompt_template: string | null
  layout_ref: string | null
  sort_order: number
  status: string
  created_at: string
  updated_at: string
}

export interface Material {
  id: number
  name: string
  file_path: string
  thumbnail_path: string | null
  tags: string[] | null
  style_tags: string[] | null
  sort_order: number
  status: string
  created_at: string
  updated_at: string
}

export interface SizePreset {
  id: number
  platform_name: string
  width: number
  height: number
  sort_order: number
  status: string
  created_at: string
  updated_at: string
}

function list<T>(path: string): Promise<{ items: T[] }> {
  return request<{ items: T[] }>(path)
}

export const listTemplates = () => list<Template>('/admin/templates')
export const createTemplate = (payload: Partial<Template>) =>
  request<Template>('/admin/templates', { method: 'POST', body: JSON.stringify(payload) })
export const updateTemplate = (id: number, payload: Partial<Template>) =>
  request<Template>(`/admin/templates/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
export const setTemplateStatus = (id: number, status: string) =>
  request<Template>(`/admin/templates/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) })

export const listMaterials = () => list<Material>('/admin/materials')
export function uploadMaterial(file: File, name: string): Promise<Material> {
  const form = new FormData()
  form.append('file', file)
  form.append('name', name)
  return request<Material>('/admin/materials', { method: 'POST', body: form })
}
export const updateMaterial = (id: number, payload: Partial<Material>) =>
  request<Material>(`/admin/materials/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
export const setMaterialStatus = (id: number, status: string) =>
  request<Material>(`/admin/materials/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) })

export const listSizes = () => list<SizePreset>('/admin/sizes')
export const createSize = (payload: Partial<SizePreset>) =>
  request<SizePreset>('/admin/sizes', { method: 'POST', body: JSON.stringify(payload) })
export const updateSize = (id: number, payload: Partial<SizePreset>) =>
  request<SizePreset>(`/admin/sizes/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
