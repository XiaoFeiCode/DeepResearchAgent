<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import axios from 'axios'

import ChatPanel from './components/ChatPanel.vue'
import WorkspaceDrawer from './components/WorkspaceDrawer.vue'
import WorkspaceRail from './components/WorkspaceRail.vue'
import type {
  AgentStatus,
  DrawerMode,
  FileItem,
  Message,
  RagflowDataset,
  RagflowDocument,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')
const WS_BASE = API_BASE.replace(/^http/, 'ws')
const THREAD_STORAGE_KEY = 'deep-agent-thread-id'

const getInitialThreadId = () => {
  const savedThreadId = sessionStorage.getItem(THREAD_STORAGE_KEY)
  if (savedThreadId) return savedThreadId

  const newThreadId = crypto.randomUUID()
  sessionStorage.setItem(THREAD_STORAGE_KEY, newThreadId)
  return newThreadId
}

const inputQuery = ref('')
const messages = ref<Message[]>([])
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
let reconnectTimer: number | undefined

const latestAiMessage = computed(() => [...messages.value].reverse().find((message) => message.role === 'ai'))
const latestLogs = computed(() => latestAiMessage.value?.logs?.slice(-4) ?? [])
const selectedDataset = computed(() => ragflowDatasets.value.find((dataset) => dataset.id === selectedDatasetId.value))
const canSend = computed(() => status.value !== 'running' && (inputQuery.value.trim().length > 0 || selectedFiles.value.length > 0))

const fetchConversationMessages = async (threadId = currentThreadId.value) => {
  try {
    const response = await axios.get(
      `${API_BASE}/api/conversations/${encodeURIComponent(threadId)}/messages`,
    )
    messages.value = (response.data.messages ?? []).map((message: any): Message => ({
      role: message.role === 'assistant' ? 'ai' : message.role,
      content: message.content,
      timestamp: message.timestamp,
    }))
  } catch (error: any) {
    if (error.response?.status !== 503) {
      console.error('Failed to restore conversation history', error)
    }
  }
}

const starterPrompts = [
  '查看 RAGFlow 里有哪些知识库',
  '查询数据库里的某个条目',
  '帮我生成一份空调安装说明 PDF',
  '把上传文件整理成摘要',
]

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
    isSidebarOpen.value = true
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
        const fileUrl = `${currentSessionUrl.value}/${eventData.args.filename}`
        if (!lastAiMessage.files.some((file) => file.name === eventData.args.filename)) {
          lastAiMessage.files.push({ name: eventData.args.filename, path: eventData.args.filename, url: fileUrl })
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

  if (event === 'task_result') {
    if (lastAiMessage) lastAiMessage.content = eventData.result
    else messages.value.push({ role: 'ai', content: eventData.result, timestamp: Date.now() })
    status.value = 'idle'
    fetchFiles()
  }

  if (event === 'error') {
    messages.value.push({ role: 'system', content: `Error: ${message}`, timestamp: Date.now() })
    status.value = 'idle'
  }
}

const connectWebSocket = () => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  socket.value?.close()
  const websocket = new WebSocket(`${WS_BASE}/ws/${currentThreadId.value}`)
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

const startNewChat = async () => {
  currentThreadId.value = crypto.randomUUID()
  sessionStorage.setItem(THREAD_STORAGE_KEY, currentThreadId.value)
  messages.value = []
  fileList.value = []
  selectedFiles.value = []
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  status.value = 'idle'
  try {
    await axios.post(`${API_BASE}/api/conversations`, { thread_id: currentThreadId.value })
  } catch (error: any) {
    if (error.response?.status !== 503) console.error('Failed to create conversation', error)
  }
  connectWebSocket()
}

onMounted(async () => {
  isSidebarOpen.value = window.innerWidth > 1120
  await fetchConversationMessages()
  connectWebSocket()
})

onBeforeUnmount(() => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  const websocket = socket.value
  socket.value = null
  websocket?.close()
})
</script>

<template>
  <div class="app-shell" :class="{ 'drawer-visible': isSidebarOpen }">
    <WorkspaceRail :status="status" :thread-id="currentThreadId" :file-count="fileList.length" :logs="latestLogs" />

    <main class="conversation-pane">
      <header class="topbar">
        <div>
          <span class="eyebrow">Agent Console</span>
          <h1>把问题、知识库和文件串起来</h1>
        </div>
        <div class="topbar-actions">
          <button class="files-toggle" type="button" @click="openFilesDrawer">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h4l2 2h5A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-11Z" /></svg>
            文件
          </button>
          <button class="files-toggle knowledge-toggle" type="button" @click="openKnowledgeDrawer">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v13A2.5 2.5 0 0 1 17.5 21h-11A2.5 2.5 0 0 1 4 18.5v-13Z" />
              <path d="M8 7h8M8 11h8M8 15h5" />
            </svg>
            知识库
          </button>
          <button class="new-chat-button" type="button" :disabled="status === 'running'" @click="startNewChat">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            新会话
          </button>
        </div>
      </header>

      <ChatPanel
        :messages="messages"
        :status="status"
        :input-query="inputQuery"
        :selected-files="selectedFiles"
        :can-send="canSend"
        :starter-prompts="starterPrompts"
        @update:input-query="inputQuery = $event"
        @send="sendMessage"
        @file-change="handleFileChange"
        @remove-file="selectedFiles.splice($event, 1)"
        @use-prompt="inputQuery = $event"
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
      @close="isSidebarOpen = false"
      @refresh="drawerMode === 'knowledge' ? fetchRagflowDatasets() : fetchFiles()"
      @select-dataset="selectRagflowDataset"
      @kb-file-change="handleKbFileChange"
      @remove-kb-file="selectedKbFiles.splice($event, 1)"
      @upload-kb-files="uploadKnowledgeFiles"
      @parse-document="parseKnowledgeDocument"
      @delete-document="deleteKnowledgeDocument"
    />
  </div>
</template>
