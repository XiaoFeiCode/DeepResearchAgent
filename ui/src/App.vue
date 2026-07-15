<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import axios from 'axios'

import ChatPanel from './components/ChatPanel.vue'
import WorkspaceDrawer from './components/WorkspaceDrawer.vue'
import WorkspaceRail from './components/WorkspaceRail.vue'
import type {
  AgentStatus,
  ConversationSummary,
  DrawerMode,
  FileItem,
  ImageKnowledgeItem,
  Message,
  RagflowDataset,
  RagflowDocument,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')
const WS_BASE = API_BASE.replace(/^http/, 'ws')
const THREAD_STORAGE_KEY = 'deep-agent-thread-id'
const AUTH_STORAGE_KEY = 'deep-agent-access-token'

const getInitialThreadId = () => {
  const savedThreadId = sessionStorage.getItem(THREAD_STORAGE_KEY)
  if (savedThreadId) return savedThreadId

  const newThreadId = crypto.randomUUID()
  sessionStorage.setItem(THREAD_STORAGE_KEY, newThreadId)
  return newThreadId
}

const inputQuery = ref('')
const messages = ref<Message[]>([])
const conversations = ref<ConversationSummary[]>([])
const status = ref<AgentStatus>('idle')
const socket = ref<WebSocket | null>(null)
const currentThreadId = ref(getInitialThreadId())
const currentSessionPath = ref('')
const currentSessionUrl = ref('')
const isSidebarOpen = ref(false)
const drawerMode = ref<DrawerMode>('files')
const fileList = ref<FileItem[]>([])
const selectedFiles = ref<File[]>([])
const ragflowDatasets = ref<RagflowDataset[]>([])
const ragflowDocuments = ref<RagflowDocument[]>([])
const selectedDatasetId = ref('')
const selectedKbFiles = ref<File[]>([])
const ragflowLoading = ref(false)
const ragflowUploading = ref(false)
const ragflowMessage = ref('')
const ragflowError = ref('')
const imageKnowledgeItems = ref<ImageKnowledgeItem[]>([])
const selectedImageFiles = ref<File[]>([])
const imageDescription = ref('')
const imageKnowledgeLoading = ref(false)
const imageKnowledgeUploading = ref(false)
const imageKnowledgeMessage = ref('')
const imageKnowledgeError = ref('')
const authToken = ref(localStorage.getItem(AUTH_STORAGE_KEY) || '')
const authUser = ref('')
const loginUsername = ref('admin')
const loginPassword = ref('')
const authLoading = ref(false)
const authError = ref('')
let reconnectTimer: number | undefined
const imageObjectUrls = new Map<string, string>()

const isAuthenticated = computed(() => authToken.value.length > 0)
const selectedDataset = computed(() => ragflowDatasets.value.find((dataset) => dataset.id === selectedDatasetId.value))
const canSend = computed(() => status.value !== 'running' && (inputQuery.value.trim().length > 0 || selectedFiles.value.length > 0))

const applyAuthHeader = (token: string) => {
  if (token) axios.defaults.headers.common.Authorization = `Bearer ${token}`
  else delete axios.defaults.headers.common.Authorization
}

const releaseImageObjectUrls = () => {
  for (const url of imageObjectUrls.values()) URL.revokeObjectURL(url)
  imageObjectUrls.clear()
}

const hydrateImageItem = async (image: ImageKnowledgeItem): Promise<ImageKnowledgeItem> => {
  const cachedUrl = imageObjectUrls.get(image.id)
  if (cachedUrl) return { ...image, previewUrl: cachedUrl }

  try {
    const response = await axios.get(`${API_BASE}${image.content_url}`, {
      responseType: 'blob',
    })
    const previewUrl = URL.createObjectURL(response.data)
    imageObjectUrls.set(image.id, previewUrl)
    return { ...image, previewUrl }
  } catch (error) {
    console.error(`Failed to load image preview: ${image.filename}`, error)
    return image
  }
}

const hydrateImageItems = (images: ImageKnowledgeItem[]) => Promise.all(images.map(hydrateImageItem))

const clearAuthState = () => {
  authToken.value = ''
  authUser.value = ''
  localStorage.removeItem(AUTH_STORAGE_KEY)
  applyAuthHeader('')
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  const websocket = socket.value
  socket.value = null
  websocket?.close()
  releaseImageObjectUrls()
}

const validateToken = async () => {
  if (!authToken.value) return false
  applyAuthHeader(authToken.value)
  try {
    const response = await axios.get(`${API_BASE}/api/auth/me`)
    authUser.value = response.data.username
    return true
  } catch {
    clearAuthState()
    return false
  }
}

const login = async () => {
  authLoading.value = true
  authError.value = ''
  try {
    const formData = new URLSearchParams()
    formData.set('username', loginUsername.value)
    formData.set('password', loginPassword.value)
    const response = await axios.post(`${API_BASE}/api/auth/token`, formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    authToken.value = response.data.access_token
    localStorage.setItem(AUTH_STORAGE_KEY, authToken.value)
    applyAuthHeader(authToken.value)
    await validateToken()
    await fetchConversationMessages()
    await fetchConversations()
    connectWebSocket()
  } catch (error: any) {
    authError.value = error.response?.data?.detail || error.message || '登录失败'
  } finally {
    authLoading.value = false
  }
}

const logout = () => {
  clearAuthState()
  messages.value = []
  conversations.value = []
  fileList.value = []
  selectedFiles.value = []
  imageKnowledgeItems.value = []
  selectedImageFiles.value = []
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  status.value = 'idle'
}

axios.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestUrl = error.config?.url || ''
    if (error.response?.status === 401 && !requestUrl.includes('/api/auth/token')) {
      clearAuthState()
      authError.value = '登录已过期，请重新登录'
    }
    return Promise.reject(error)
  },
)

const fetchConversationMessages = async (threadId = currentThreadId.value) => {
  try {
    const response = await axios.get(
      `${API_BASE}/api/conversations/${encodeURIComponent(threadId)}/messages`,
    )
    messages.value = (response.data.messages ?? []).map((message: any): Message => ({
      role: message.role === 'assistant' ? 'ai' : message.role,
      content: message.content,
      images: message.metadata?.images ?? [],
      timestamp: message.timestamp,
    }))
    await Promise.all(
      messages.value.map(async (message) => {
        if (message.images?.length) message.images = await hydrateImageItems(message.images)
      }),
    )
  } catch (error: any) {
    if (error.response?.status === 404) {
      currentThreadId.value = crypto.randomUUID()
      sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
      messages.value = []
      return
    }
    if (error.response?.status !== 503) {
      console.error('Failed to restore conversation history', error)
    }
  }
}

const fetchConversations = async () => {
  try {
    const response = await axios.get(`${API_BASE}/api/conversations`, {
      params: { limit: 100 },
    })
    conversations.value = (response.data.conversations ?? []).filter(
      (conversation: ConversationSummary) => conversation.title !== '新会话',
    )
  } catch (error: any) {
    if (error.response?.status !== 503) console.error('Failed to load conversations', error)
  }
}

const selectConversation = async (threadId: string) => {
  if (status.value === 'running' || threadId === currentThreadId.value) return

  currentThreadId.value = threadId
  sessionStorage.setItem(THREAD_STORAGE_KEY, threadId)
  messages.value = []
  fileList.value = []
  selectedFiles.value = []
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  await fetchConversationMessages(threadId)
  connectWebSocket()
}

const deleteConversation = async (conversation: ConversationSummary) => {
  if (status.value === 'running') return
  if (!window.confirm(`确定删除会话“${conversation.title}”吗？删除后无法恢复。`)) return

  try {
    await axios.delete(
      `${API_BASE}/api/conversations/${encodeURIComponent(conversation.id)}`,
    )
    conversations.value = conversations.value.filter((item) => item.id !== conversation.id)

    if (conversation.id === currentThreadId.value) {
      currentThreadId.value = crypto.randomUUID()
      sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
      messages.value = []
      fileList.value = []
      selectedFiles.value = []
      currentSessionPath.value = ''
      currentSessionUrl.value = ''
      connectWebSocket()
    }
  } catch (error: any) {
    const detail = error.response?.data?.detail || error.message || '未知错误'
    messages.value.push({
      role: 'system',
      content: `删除会话失败：${detail}`,
      timestamp: Date.now(),
    })
  }
}

const fetchFiles = async () => {
  if (!currentSessionPath.value) return
  try {
    const response = await axios.get(`${API_BASE}/api/files`, {
      params: { path: currentSessionPath.value },
    })
    if (response.data.files) {
      fileList.value = response.data.files.map((file: FileItem) => ({
        ...file,
        url: `${API_BASE}/api/download?path=${encodeURIComponent(file.path)}`,
      }))
    }
  } catch (error) {
    console.error('Failed to fetch files', error)
  }
}

const showRagflowMessage = (message: string, isError = false) => {
  ragflowMessage.value = isError ? '' : message
  ragflowError.value = isError ? message : ''
}

const fetchRagflowDocuments = async (datasetId = selectedDatasetId.value) => {
  if (!datasetId) {
    ragflowDocuments.value = []
    return
  }

  try {
    ragflowLoading.value = true
    const response = await axios.get(`${API_BASE}/api/ragflow/documents`, {
      params: { dataset_name_or_id: datasetId },
    })
    if (response.data.error) {
      showRagflowMessage(response.data.error, true)
      ragflowDocuments.value = []
      return
    }
    ragflowDocuments.value = response.data.documents ?? []
  } catch (error: any) {
    showRagflowMessage(`获取知识库文档失败：${error.message || '未知错误'}`, true)
  } finally {
    ragflowLoading.value = false
  }
}

const fetchRagflowDatasets = async () => {
  try {
    ragflowLoading.value = true
    showRagflowMessage('')
    const response = await axios.get(`${API_BASE}/api/ragflow/datasets`)
    if (response.data.error) {
      showRagflowMessage(response.data.error, true)
      ragflowDatasets.value = []
      ragflowDocuments.value = []
      return
    }

    ragflowDatasets.value = response.data.datasets ?? []
    const stillExists = ragflowDatasets.value.some((dataset) => dataset.id === selectedDatasetId.value)
    if (!stillExists) selectedDatasetId.value = ragflowDatasets.value[0]?.id ?? ''
    if (selectedDatasetId.value) await fetchRagflowDocuments(selectedDatasetId.value)
  } catch (error: any) {
    showRagflowMessage(`获取知识库列表失败：${error.message || '未知错误'}`, true)
  } finally {
    ragflowLoading.value = false
  }
}

const selectRagflowDataset = async (dataset: RagflowDataset) => {
  selectedDatasetId.value = dataset.id
  await fetchRagflowDocuments(dataset.id)
}

const openFilesDrawer = () => {
  drawerMode.value = 'files'
  isSidebarOpen.value = true
  fetchFiles()
}

const openKnowledgeDrawer = () => {
  drawerMode.value = 'knowledge'
  isSidebarOpen.value = true
  fetchRagflowDatasets()
}

const showImageKnowledgeMessage = (message: string, isError = false) => {
  imageKnowledgeMessage.value = isError ? '' : message
  imageKnowledgeError.value = isError ? message : ''
}

const fetchImageKnowledge = async () => {
  try {
    imageKnowledgeLoading.value = true
    showImageKnowledgeMessage('')
    const response = await axios.get(`${API_BASE}/api/image-knowledge/images`)
    imageKnowledgeItems.value = await hydrateImageItems(response.data.images ?? [])
  } catch (error: any) {
    showImageKnowledgeMessage(
      `读取图片知识库失败：${error.response?.data?.detail || error.message || '未知错误'}`,
      true,
    )
  } finally {
    imageKnowledgeLoading.value = false
  }
}

const openImageKnowledgeDrawer = () => {
  drawerMode.value = 'images'
  isSidebarOpen.value = true
  fetchImageKnowledge()
}

const handleImageKnowledgeFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  selectedImageFiles.value = [...selectedImageFiles.value, ...Array.from(target.files)]
  target.value = ''
}

const uploadImageKnowledge = async () => {
  if (!selectedImageFiles.value.length) return
  try {
    imageKnowledgeUploading.value = true
    showImageKnowledgeMessage('')
    const formData = new FormData()
    formData.append('description', imageDescription.value)
    selectedImageFiles.value.forEach((file) => formData.append('files', file))
    const response = await axios.post(
      `${API_BASE}/api/image-knowledge/images/upload`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    const count = response.data.images?.length ?? 0
    selectedImageFiles.value = []
    imageDescription.value = ''
    showImageKnowledgeMessage(`已完成 ${count} 张图片的向量化和入库`)
    await fetchImageKnowledge()
  } catch (error: any) {
    showImageKnowledgeMessage(
      `图片入库失败：${error.response?.data?.detail || error.message || '未知错误'}`,
      true,
    )
  } finally {
    imageKnowledgeUploading.value = false
  }
}

const deleteImageKnowledge = async (image: ImageKnowledgeItem) => {
  if (!window.confirm(`确定从图片知识库删除“${image.filename}”吗？`)) return
  try {
    await axios.delete(`${API_BASE}/api/image-knowledge/images/${encodeURIComponent(image.id)}`)
    const previewUrl = imageObjectUrls.get(image.id)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    imageObjectUrls.delete(image.id)
    showImageKnowledgeMessage(`已删除图片：${image.filename}`)
    await fetchImageKnowledge()
  } catch (error: any) {
    showImageKnowledgeMessage(
      `删除图片失败：${error.response?.data?.detail || error.message || '未知错误'}`,
      true,
    )
  }
}

const handleKbFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  selectedKbFiles.value = [...selectedKbFiles.value, ...Array.from(target.files)]
  target.value = ''
}

const uploadKnowledgeFiles = async () => {
  if (!selectedDatasetId.value || selectedKbFiles.value.length === 0) return
  try {
    ragflowUploading.value = true
    showRagflowMessage('')
    const formData = new FormData()
    formData.append('dataset_name_or_id', selectedDatasetId.value)
    formData.append('parse_after_upload', 'true')
    selectedKbFiles.value.forEach((file) => formData.append('files', file))

    const response = await axios.post(`${API_BASE}/api/ragflow/documents/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (response.data.error) {
      showRagflowMessage(response.data.error, true)
      return
    }

    const names = selectedKbFiles.value.map((file) => file.name).join('、')
    selectedKbFiles.value = []
    showRagflowMessage(`已上传并提交解析：${names}`)
    await fetchRagflowDatasets()
  } catch (error: any) {
    showRagflowMessage(`上传到 RAGFlow 失败：${error.message || '未知错误'}`, true)
  } finally {
    ragflowUploading.value = false
  }
}

const parseKnowledgeDocument = async (document: RagflowDocument) => {
  if (!selectedDatasetId.value) return
  try {
    showRagflowMessage('')
    const response = await axios.post(`${API_BASE}/api/ragflow/documents/parse`, {
      dataset_name_or_id: selectedDatasetId.value,
      document_names_or_ids: document.id,
    })
    if (response.data.error) {
      showRagflowMessage(response.data.error, true)
      return
    }
    showRagflowMessage(`已提交解析：${document.name}`)
    await fetchRagflowDocuments()
  } catch (error: any) {
    showRagflowMessage(`解析文档失败：${error.message || '未知错误'}`, true)
  }
}

const deleteKnowledgeDocument = async (document: RagflowDocument) => {
  if (!selectedDatasetId.value || !window.confirm(`确定删除文档“${document.name}”吗？`)) return
  try {
    showRagflowMessage('')
    const response = await axios.post(`${API_BASE}/api/ragflow/documents/delete`, {
      dataset_name_or_id: selectedDatasetId.value,
      document_names_or_ids: document.id,
    })
    if (response.data.error) {
      showRagflowMessage(response.data.error, true)
      return
    }
    showRagflowMessage(`已删除文档：${document.name}`)
    await fetchRagflowDatasets()
  } catch (error: any) {
    showRagflowMessage(`删除文档失败：${error.message || '未知错误'}`, true)
  }
}

const handleSocketMessage = (payload: any) => {
  const { type, event, message, data: eventData } = payload
  if (type === 'pong') return
  const lastAiMessage = [...messages.value].reverse().find((item) => item.role === 'ai')

  if (event === 'session_created') {
    currentSessionPath.value = eventData.path
    const parts = eventData.path.split(/output[\\/]/)
    if (parts.length > 1) currentSessionUrl.value = `${API_BASE}/outputs/${parts[1].replace(/\\/g, '/')}`
    // 会话启动时只刷新文件状态，避免空文件抽屉遮挡聊天结果。
    fetchFiles()
  }

  if (event === 'tool_start') {
    fetchFiles()
    window.setTimeout(fetchFiles, 1800)
    if (lastAiMessage) {
      lastAiMessage.logs ??= []
      lastAiMessage.logs.push({
        type: 'tool',
        title: `使用工具：${eventData.tool_name}`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString(),
      })
      if (eventData.args?.filename && currentSessionUrl.value) {
        lastAiMessage.files ??= []
        const filePath = currentSessionPath.value
          ? `${currentSessionPath.value.replace(/\\/g, '/')}/${eventData.args.filename}`
          : eventData.args.filename
        const fileUrl = `${currentSessionUrl.value}/${eventData.args.filename}`
        if (!lastAiMessage.files.some((file) => file.name === eventData.args.filename)) {
          lastAiMessage.files.push({ name: eventData.args.filename, path: filePath, url: fileUrl })
        }
      }
    }
  }

  if (event === 'assistant_call' && lastAiMessage) {
    lastAiMessage.logs ??= []
    lastAiMessage.logs.push({
      type: 'agent',
      title: `正在使用助手：${eventData.assistant_name}`,
      details: eventData.args,
      timestamp: new Date().toLocaleTimeString(),
    })
  }

  if (event === 'image_search_result' && lastAiMessage) {
    const images = (eventData.images ?? []) as ImageKnowledgeItem[]
    lastAiMessage.images = images
    void hydrateImageItems(images).then((hydrated) => {
      lastAiMessage.images = hydrated
    })
  }

  if (event === 'task_result') {
    if (lastAiMessage) lastAiMessage.content = eventData.result
    else messages.value.push({ role: 'ai', content: eventData.result, timestamp: Date.now() })
    status.value = 'idle'
    fetchFiles()
    fetchConversations()
  }

  if (event === 'error') {
    messages.value.push({ role: 'system', content: `Error: ${message}`, timestamp: Date.now() })
    status.value = 'idle'
  }
}

const connectWebSocket = () => {
  if (!authToken.value) return
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  socket.value?.close()
  const websocket = new WebSocket(`${WS_BASE}/ws/${currentThreadId.value}?token=${encodeURIComponent(authToken.value)}`)
  websocket.onmessage = (event) => {
    try {
      handleSocketMessage(JSON.parse(event.data))
    } catch (error) {
      console.error('Error parsing WebSocket message', error)
    }
  }
  websocket.onclose = () => {
    if (socket.value === websocket) reconnectTimer = window.setTimeout(connectWebSocket, 3000)
  }
  socket.value = websocket
}

const uploadSelectedFiles = async (aiMessage: Message) => {
  if (selectedFiles.value.length === 0) return
  aiMessage.logs ??= []
  aiMessage.logs.push({
    type: 'info',
    title: `上传文件：${selectedFiles.value.length} 个`,
    details: selectedFiles.value.map((file) => ({ name: file.name, size: file.size })),
    timestamp: new Date().toLocaleTimeString(),
  })

  const formData = new FormData()
  formData.append('thread_id', currentThreadId.value)
  selectedFiles.value.forEach((file) => formData.append('files', file))
  await axios.post(`${API_BASE}/api/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  selectedFiles.value = []
  aiMessage.logs.push({ type: 'success', title: '文件上传完成', details: null, timestamp: new Date().toLocaleTimeString() })
}

const sendMessage = async () => {
  if (!canSend.value) return
  const query = inputQuery.value.trim() || '请分析我上传的文件'
  inputQuery.value = ''
  status.value = 'running'
  messages.value.push({ role: 'user', content: query, timestamp: Date.now() })

  const aiMessage: Message = { role: 'ai', content: '', logs: [], files: [], timestamp: Date.now() }
  messages.value.push(aiMessage)
  try {
    await uploadSelectedFiles(aiMessage)
    const response = await axios.post(`${API_BASE}/api/task`, { query, thread_id: currentThreadId.value })
    if (response.data?.thread_id) {
      currentThreadId.value = response.data.thread_id
      sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
    }
  } catch (error: any) {
    messages.value.push({ role: 'system', content: `请求失败：${error.message || '未知错误'}`, timestamp: Date.now() })
    status.value = 'idle'
  }
}

const handleFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
  target.value = ''
}

const downloadFile = async (file: FileItem) => {
  try {
    const response = await axios.get(`${API_BASE}/api/download`, {
      params: { path: file.path },
      responseType: 'blob',
    })
    const blobUrl = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = file.name
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(blobUrl)
  } catch (error: any) {
    messages.value.push({ role: 'system', content: `下载失败：${error.message || '未知错误'}`, timestamp: Date.now() })
  }
}

const startNewChat = async () => {
  currentThreadId.value = crypto.randomUUID()
  sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
  messages.value = []
  fileList.value = []
  selectedFiles.value = []
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  status.value = 'idle'
  connectWebSocket()
}

onMounted(async () => {
  isSidebarOpen.value = false
  const ok = await validateToken()
  if (ok) {
    await fetchConversationMessages()
    await fetchConversations()
    connectWebSocket()
  }
})

onBeforeUnmount(() => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  const websocket = socket.value
  socket.value = null
  websocket?.close()
  releaseImageObjectUrls()
})
</script>

<template>
  <main v-if="!isAuthenticated" class="auth-page">
    <form class="auth-card" @submit.prevent="login">
      <span class="eyebrow">Secure Console</span>
      <h1>登录 DeepAgent Studio</h1>
      <p>访问任务执行、知识库管理和会话文件前，需要先通过 API 鉴权。</p>

      <label>
        用户名
        <input v-model="loginUsername" autocomplete="username" />
      </label>
      <label>
        密码
        <input v-model="loginPassword" type="password" autocomplete="current-password" />
      </label>
      <div v-if="authError" class="auth-error">{{ authError }}</div>
      <button class="auth-submit" type="submit" :disabled="authLoading">
        {{ authLoading ? '登录中...' : '登录' }}
      </button>
    </form>
  </main>

  <div v-else class="app-shell" :class="{ 'drawer-visible': isSidebarOpen }">
    <WorkspaceRail
      :status="status"
      :thread-id="currentThreadId"
      :file-count="fileList.length"
      :conversations="conversations"
      :user-name="authUser || loginUsername"
      @new-chat="startNewChat"
      @open-files="openFilesDrawer"
      @open-knowledge="openKnowledgeDrawer"
      @open-images="openImageKnowledgeDrawer"
      @select-conversation="selectConversation"
      @delete-conversation="deleteConversation"
      @logout="logout"
    />

    <main class="conversation-pane">
      <header class="topbar">
        <div class="conversation-title">
          <h1>DeepAgent</h1>
          <span class="run-status" :class="status">{{ status === 'running' ? '执行中' : '就绪' }}</span>
        </div>
        <div class="mobile-toolbar">
          <button type="button" title="文件" aria-label="文件" @click="openFilesDrawer">文件</button>
          <button type="button" title="知识库" aria-label="知识库" @click="openKnowledgeDrawer">知识库</button>
          <button type="button" title="新对话" aria-label="新对话" :disabled="status === 'running'" @click="startNewChat">新对话</button>
        </div>
      </header>

      <ChatPanel
        :messages="messages"
        :status="status"
        :input-query="inputQuery"
        :selected-files="selectedFiles"
        :can-send="canSend"
        @update:input-query="inputQuery = $event"
        @send="sendMessage"
        @file-change="handleFileChange"
        @remove-file="selectedFiles.splice($event, 1)"
        @download-file="downloadFile"
      />
    </main>

    <WorkspaceDrawer
      v-if="isSidebarOpen"
      :mode="drawerMode"
      :files="fileList"
      :datasets="ragflowDatasets"
      :documents="ragflowDocuments"
      :selected-dataset="selectedDataset"
      :selected-dataset-id="selectedDatasetId"
      :selected-kb-files="selectedKbFiles"
      :ragflow-loading="ragflowLoading"
      :ragflow-uploading="ragflowUploading"
      :ragflow-message="ragflowMessage"
      :ragflow-error="ragflowError"
      :image-knowledge-items="imageKnowledgeItems"
      :selected-image-files="selectedImageFiles"
      :image-description="imageDescription"
      :image-knowledge-loading="imageKnowledgeLoading"
      :image-knowledge-uploading="imageKnowledgeUploading"
      :image-knowledge-message="imageKnowledgeMessage"
      :image-knowledge-error="imageKnowledgeError"
      @close="isSidebarOpen = false"
      @refresh="drawerMode === 'knowledge' ? fetchRagflowDatasets() : drawerMode === 'images' ? fetchImageKnowledge() : fetchFiles()"
      @download-file="downloadFile"
      @select-dataset="selectRagflowDataset"
      @kb-file-change="handleKbFileChange"
      @remove-kb-file="selectedKbFiles.splice($event, 1)"
      @upload-kb-files="uploadKnowledgeFiles"
      @parse-document="parseKnowledgeDocument"
      @delete-document="deleteKnowledgeDocument"
      @update:image-description="imageDescription = $event"
      @image-file-change="handleImageKnowledgeFileChange"
      @remove-image-file="selectedImageFiles.splice($event, 1)"
      @upload-images="uploadImageKnowledge"
      @delete-image="deleteImageKnowledge"
    />
  </div>
</template>
