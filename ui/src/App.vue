<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  API_BASE,
  WS_BASE,
  authApi,
  conversationApi,
  fileApi,
  getErrorMessage,
  getErrorStatus,
  registerUnauthorizedHandler,
  removeResponseInterceptor,
  setAccessToken,
  taskApi,
} from './api/client'
import ChatPanel from './components/ChatPanel.vue'
import KnowledgeBasePage from './components/KnowledgeBasePage.vue'
import WorkspaceDrawer from './components/WorkspaceDrawer.vue'
import WorkspaceRail from './components/WorkspaceRail.vue'
import { useImageAssets } from './composables/useImageAssets'
import { useRagflowKnowledge } from './composables/useRagflowKnowledge'
import type {
  AgentStatus,
  ConversationSummary,
  FileItem,
  Message,
  MessageAttachment,
} from './types'

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
const activeView = ref<'chat' | 'knowledge'>('chat')
const fileList = ref<FileItem[]>([])
const selectedFiles = ref<File[]>([])
const authToken = ref(localStorage.getItem(AUTH_STORAGE_KEY) || '')
const authUser = ref('')
const loginUsername = ref('admin')
const loginPassword = ref('')
const authLoading = ref(false)
const authError = ref('')
let reconnectTimer: number | undefined

const imageAssets = useImageAssets()
const {
  adoptAttachmentPreview,
  createPendingAttachments,
  hydrateImageItems,
  hydrateMessages,
  release: releaseImageAssets,
  rememberImageMetadata,
  resolveReferencedImages,
} = imageAssets

const {
  datasets: ragflowDatasets,
  deleteDocument: deleteKnowledgeDocument,
  documents: ragflowDocuments,
  createDataset,
  creating: ragflowCreating,
  error: ragflowError,
  fetchDatasets: fetchRagflowDatasets,
  handleFileChange: handleKbFileChange,
  loading: ragflowLoading,
  message: ragflowMessage,
  newDatasetDescription,
  newDatasetName,
  parseDocument: parseKnowledgeDocument,
  selectedDataset,
  selectedDatasetId,
  selectedFiles: selectedKbFiles,
  selectDataset: selectRagflowDataset,
  uploading: ragflowUploading,
  uploadFiles: uploadKnowledgeFiles,
} = useRagflowKnowledge()


const isAuthenticated = computed(() => authToken.value.length > 0)
const canSend = computed(() => status.value !== 'running' && (inputQuery.value.trim().length > 0 || selectedFiles.value.length > 0))

const applyAuthHeader = (token: string) => {
  setAccessToken(token)
}

const clearAuthState = () => {
  authToken.value = ''
  authUser.value = ''
  localStorage.removeItem(AUTH_STORAGE_KEY)
  applyAuthHeader('')
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  const websocket = socket.value
  socket.value = null
  websocket?.close()
  releaseImageAssets()
}

const validateToken = async () => {
  if (!authToken.value) return false
  applyAuthHeader(authToken.value)
  try {
    const data = await authApi.currentUser()
    authUser.value = data.username
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
    const data = await authApi.login(loginUsername.value, loginPassword.value)
    authToken.value = data.access_token
    localStorage.setItem(AUTH_STORAGE_KEY, authToken.value)
    applyAuthHeader(authToken.value)
    await validateToken()
    await fetchConversationMessages()
    await fetchConversations()
    connectWebSocket()
  } catch (error) {
    authError.value = getErrorMessage(error, '登录失败')
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
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  status.value = 'idle'
}

const authInterceptorId = registerUnauthorizedHandler(() => {
  clearAuthState()
  authError.value = '登录已过期，请重新登录'
})

const fetchConversationMessages = async (threadId = currentThreadId.value) => {
  try {
    const data = await conversationApi.messages(threadId)
    messages.value = (data.messages ?? []).map((message: any): Message => ({
      role: message.role === 'assistant' ? 'ai' : message.role,
      content: message.content,
      images: message.metadata?.images ?? [],
      attachments: message.metadata?.attachments ?? [],
      timestamp: message.timestamp,
    }))
    await hydrateMessages(messages.value)
  } catch (error) {
    if (getErrorStatus(error) === 404) {
      currentThreadId.value = crypto.randomUUID()
      sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
      messages.value = []
      return
    }
    if (getErrorStatus(error) !== 503) {
      console.error('恢复会话历史失败', error)
    }
  }
}

const fetchConversations = async () => {
  try {
    const data = await conversationApi.list()
    conversations.value = (data.conversations ?? []).filter(
      (conversation: ConversationSummary) => conversation.title !== '新会话',
    )
  } catch (error) {
    if (getErrorStatus(error) !== 503) console.error('加载会话列表失败', error)
  }
}

const selectConversation = async (threadId: string) => {
  if (status.value === 'running' || threadId === currentThreadId.value) return

  activeView.value = 'chat'
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
    await conversationApi.remove(conversation.id)
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
  } catch (error) {
    const detail = getErrorMessage(error)
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
    const data = await fileApi.list(currentSessionPath.value)
    if (data.files) {
      fileList.value = data.files.map((file: FileItem) => ({
        ...file,
        url: `${API_BASE}/api/download?path=${encodeURIComponent(file.path)}`,
      }))
    }
  } catch (error) {
    console.error('读取会话文件失败', error)
  }
}

const openFilesDrawer = () => {
  isSidebarOpen.value = true
  fetchFiles()
}

const openKnowledgeDrawer = () => {
  activeView.value = 'knowledge'
  isSidebarOpen.value = false
  fetchRagflowDatasets()
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
    const images = eventData.images ?? []
    rememberImageMetadata(images)
    lastAiMessage.images = images
    void hydrateImageItems(images).then((hydrated) => {
      lastAiMessage.images = hydrated
    })
  }

  if (event === 'task_result') {
    let resultMessage = lastAiMessage
    if (resultMessage) resultMessage.content = eventData.result
    else {
      resultMessage = { role: 'ai', content: eventData.result, timestamp: Date.now() }
      messages.value.push(resultMessage)
    }
    void resolveReferencedImages([resultMessage]).then(async () => {
      if (resultMessage?.images?.length) {
        resultMessage.images = await hydrateImageItems(resultMessage.images)
      }
    })
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
      console.error('解析 WebSocket 消息失败', error)
    }
  }
  websocket.onclose = () => {
    if (socket.value === websocket) reconnectTimer = window.setTimeout(connectWebSocket, 3000)
  }
  socket.value = websocket
}

const uploadSelectedFiles = async (
  aiMessage: Message,
  pendingAttachments: MessageAttachment[],
): Promise<MessageAttachment[]> => {
  if (selectedFiles.value.length === 0) return []
  aiMessage.logs ??= []
  aiMessage.logs.push({
    type: 'info',
    title: `上传文件：${selectedFiles.value.length} 个`,
    details: selectedFiles.value.map((file) => ({ name: file.name, size: file.size })),
    timestamp: new Date().toLocaleTimeString(),
  })

  const data = await fileApi.upload(currentThreadId.value, selectedFiles.value)
  const attachments = (data.files ?? []).map((item: any, index: number) => {
    const pending = pendingAttachments[index]
    const attachment: MessageAttachment = typeof item === 'string'
      ? {
          name: item,
          content_type: pending?.content_type || 'application/octet-stream',
          size: pending?.size || 0,
          content_url: `/api/uploads/${encodeURIComponent(currentThreadId.value)}/${encodeURIComponent(item)}`,
        }
      : item
    adoptAttachmentPreview(pending, attachment)
    return attachment
  })
  selectedFiles.value = []
  aiMessage.logs.push({ type: 'success', title: '文件上传完成', details: null, timestamp: new Date().toLocaleTimeString() })
  return attachments
}

const sendMessage = async () => {
  if (!canSend.value) return
  const query = inputQuery.value.trim() || '请分析我上传的文件'
  inputQuery.value = ''
  status.value = 'running'
  const pendingAttachments = createPendingAttachments([...selectedFiles.value])
  const userMessage: Message = {
    role: 'user',
    content: query,
    attachments: pendingAttachments,
    timestamp: Date.now(),
  }
  messages.value.push(userMessage)

  const aiMessage: Message = { role: 'ai', content: '', logs: [], files: [], timestamp: Date.now() }
  messages.value.push(aiMessage)
  try {
    const attachments = await uploadSelectedFiles(aiMessage, pendingAttachments)
    userMessage.attachments = attachments
    const data = await taskApi.start(query, currentThreadId.value, attachments)
    if (data?.thread_id) {
      currentThreadId.value = data.thread_id
      sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
    }
  } catch (error) {
    messages.value.push({ role: 'system', content: `请求失败：${getErrorMessage(error)}`, timestamp: Date.now() })
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
    const blobUrl = URL.createObjectURL(await fileApi.download(file.path))
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = file.name
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(blobUrl)
  } catch (error) {
    messages.value.push({ role: 'system', content: `下载失败：${getErrorMessage(error)}`, timestamp: Date.now() })
  }
}

const startNewChat = async () => {
  activeView.value = 'chat'
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
  removeResponseInterceptor(authInterceptorId)
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  const websocket = socket.value
  socket.value = null
  websocket?.close()
  releaseImageAssets()
})
</script>

<template>
  <main v-if="!isAuthenticated" class="auth-page">
    <form class="auth-card" @submit.prevent="login">
      <span class="eyebrow">Secure Console</span>
      <h1>登录 OmniResearch</h1>
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
      :active-view="activeView"
      @new-chat="startNewChat"
      @open-files="openFilesDrawer"
      @open-knowledge="openKnowledgeDrawer"
      @select-conversation="selectConversation"
      @delete-conversation="deleteConversation"
      @logout="logout"
    />

    <main class="conversation-pane">
      <template v-if="activeView === 'chat'">
        <header class="topbar">
          <div class="conversation-title">
            <h1>OmniResearch</h1>
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
      </template>

      <KnowledgeBasePage
        v-else
        :datasets="ragflowDatasets"
        :documents="ragflowDocuments"
        :selected-dataset="selectedDataset"
        :selected-dataset-id="selectedDatasetId"
        :selected-files="selectedKbFiles"
        :loading="ragflowLoading"
        :uploading="ragflowUploading"
        :creating="ragflowCreating"
        :message="ragflowMessage"
        :error="ragflowError"
        :new-dataset-name="newDatasetName"
        :new-dataset-description="newDatasetDescription"
        @back="activeView = 'chat'"
        @refresh="fetchRagflowDatasets"
        @create="createDataset"
        @update:new-dataset-name="newDatasetName = $event"
        @update:new-dataset-description="newDatasetDescription = $event"
        @select="selectRagflowDataset"
        @file-change="handleKbFileChange"
        @remove-file="selectedKbFiles.splice($event, 1)"
        @upload="uploadKnowledgeFiles"
        @parse="parseKnowledgeDocument"
        @delete="deleteKnowledgeDocument"
      />
    </main>

    <WorkspaceDrawer
      v-if="isSidebarOpen"
      :files="fileList"
      @close="isSidebarOpen = false"
      @refresh="fetchFiles"
      @download-file="downloadFile"
    />
  </div>
</template>
