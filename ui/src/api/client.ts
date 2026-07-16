import axios from 'axios'

import type { MessageAttachment } from '../types'

export const API_BASE = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')
export const WS_BASE = API_BASE.replace(/^http/, 'ws')

export const apiClient = axios.create({ baseURL: API_BASE })

export const setAccessToken = (token: string) => {
  if (token) apiClient.defaults.headers.common.Authorization = `Bearer ${token}`
  else delete apiClient.defaults.headers.common.Authorization
}

export const registerUnauthorizedHandler = (handler: () => void) => (
  apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
      const requestUrl = error.config?.url || ''
      if (error.response?.status === 401 && !requestUrl.includes('/api/auth/token')) {
        handler()
      }
      return Promise.reject(error)
    },
  )
)

export const removeResponseInterceptor = (interceptorId: number) => {
  apiClient.interceptors.response.eject(interceptorId)
}

export const getErrorMessage = (error: unknown, fallback = '未知错误') => {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.detail || error.message || fallback
  }
  return error instanceof Error ? error.message : fallback
}

export const getErrorStatus = (error: unknown) => (
  axios.isAxiosError(error) ? error.response?.status : undefined
)

export const authApi = {
  async login(username: string, password: string) {
    const formData = new URLSearchParams()
    formData.set('username', username)
    formData.set('password', password)
    const response = await apiClient.post('/api/auth/token', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return response.data
  },
  async currentUser() {
    const response = await apiClient.get('/api/auth/me')
    return response.data
  },
}

export const conversationApi = {
  async list(limit = 100) {
    const response = await apiClient.get('/api/conversations', { params: { limit } })
    return response.data
  },
  async messages(threadId: string) {
    const response = await apiClient.get(
      `/api/conversations/${encodeURIComponent(threadId)}/messages`,
    )
    return response.data
  },
  async remove(threadId: string) {
    await apiClient.delete(`/api/conversations/${encodeURIComponent(threadId)}`)
  },
}

export const fileApi = {
  async list(path: string) {
    const response = await apiClient.get('/api/files', { params: { path } })
    return response.data
  },
  async upload(threadId: string, files: File[]) {
    const formData = new FormData()
    formData.append('thread_id', threadId)
    files.forEach((file) => formData.append('files', file))
    const response = await apiClient.post('/api/upload', formData)
    return response.data
  },
  async download(path: string) {
    const response = await apiClient.get('/api/download', {
      params: { path },
      responseType: 'blob',
    })
    return response.data as Blob
  },
}

export const taskApi = {
  async start(query: string, threadId: string, attachments: MessageAttachment[]) {
    const response = await apiClient.post('/api/task', {
      query,
      thread_id: threadId,
      attachment_names: attachments.map((attachment) => attachment.name),
    })
    return response.data
  },
}

export const ragflowApi = {
  async createDataset(name: string, description: string) {
    const response = await apiClient.post('/api/ragflow/datasets', { name, description })
    return response.data
  },
  async datasets() {
    const response = await apiClient.get('/api/ragflow/datasets')
    return response.data
  },
  async documents(datasetId: string) {
    const response = await apiClient.get('/api/ragflow/documents', {
      params: { dataset_name_or_id: datasetId },
    })
    return response.data
  },
  async uploadDocuments(datasetId: string, files: File[]) {
    const formData = new FormData()
    formData.append('dataset_name_or_id', datasetId)
    formData.append('parse_after_upload', 'true')
    files.forEach((file) => formData.append('files', file))
    const response = await apiClient.post('/api/ragflow/documents/upload', formData)
    return response.data
  },
  async parseDocument(datasetId: string, documentId: string) {
    const response = await apiClient.post('/api/ragflow/documents/parse', {
      dataset_name_or_id: datasetId,
      document_names_or_ids: documentId,
    })
    return response.data
  },
  async deleteDocument(datasetId: string, documentId: string) {
    const response = await apiClient.post('/api/ragflow/documents/delete', {
      dataset_name_or_id: datasetId,
      document_names_or_ids: documentId,
    })
    return response.data
  },
}
