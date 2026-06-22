<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import axios from 'axios'
import { marked } from 'marked'

interface Message {
  role: 'user' | 'ai' | 'system'
  content: string
  logs?: LogItem[]
  files?: FileItem[]
  timestamp?: number
}

interface LogItem {
  type: string
  title: string
  details: unknown
  timestamp: string
}

interface FileItem {
  name: string
  path: string
  url: string
  size?: number
  mtime?: number
}

interface RagflowDataset {
  id: string
  name: string
  description?: string
  doc_num?: number
  chunk_num?: number
  language?: string
  parser_id?: string
}

interface RagflowDocument {
  id: string
  name: string
  run?: string | number | null
  progress?: number | string | null
  chunk_count?: number | null
  token_count?: number | null
  create_date?: string
  update_date?: string
}

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')
const WS_BASE = API_BASE.replace(/^http/, 'ws')

const inputQuery = ref('')
const messages = ref<Message[]>([])
const status = ref<'idle' | 'running'>('idle')
const socket = ref<WebSocket | null>(null)
const currentSessionPath = ref('')
const currentSessionUrl = ref('')
const messagesEndRef = ref<HTMLElement | null>(null)
const isSidebarOpen = ref(false)
const drawerMode = ref<'files' | 'knowledge'>('files')
const fileList = ref<FileItem[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const kbFileInputRef = ref<HTMLInputElement | null>(null)
const ragflowDatasets = ref<RagflowDataset[]>([])
const ragflowDocuments = ref<RagflowDocument[]>([])
const selectedDatasetId = ref('')
const selectedKbFiles = ref<File[]>([])
const ragflowLoading = ref(false)
const ragflowUploading = ref(false)
const ragflowMessage = ref('')
const ragflowError = ref('')
const getInitialThreadId = () => {
  const savedThreadId = localStorage.getItem('deep-agent-thread-id')
  if (savedThreadId) return savedThreadId

  const newThreadId = crypto.randomUUID()
  localStorage.setItem('deep-agent-thread-id', newThreadId)
  return newThreadId
}

const currentThreadId = ref(getInitialThreadId())

const isWelcomeScreen = computed(() => messages.value.length === 0)
const latestAiMessage = computed(() => [...messages.value].reverse().find((message) => message.role === 'ai'))
const latestLogs = computed(() => latestAiMessage.value?.logs?.slice(-4) ?? [])
const selectedDataset = computed(() => {
  return ragflowDatasets.value.find((dataset) => dataset.id === selectedDatasetId.value)
})
const canSend = computed(() => {
  return status.value !== 'running' && (inputQuery.value.trim().length > 0 || selectedFiles.value.length > 0)
})

const starterPrompts = [
  '查看 RAGFlow 里有哪些知识库',
  '查询数据库里的某个条目',
  '帮我生成一份空调安装说明 PDF',
  '把上传文件整理成摘要'
]

const scrollToBottom = async () => {
  await nextTick()
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
}

const formatBytes = (size?: number) => {
  if (!size) return '0 KB'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const formatTime = (timestamp?: number) => {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const getFileTag = (name: string) => {
  const suffix = name.split('.').pop()?.toUpperCase()
  return suffix ? suffix.slice(0, 4) : 'FILE'
}

const normalizeTitle = (title: string) => {
  return title
    .replace('姝ｅ湪浣跨敤鍔╂墜锛?', '正在使用助手：')
    .replace('浣跨敤鐨勫伐鍏凤細', '使用工具：')
}

const fetchFiles = async () => {
  if (!currentSessionPath.value) return
  try {
    const res = await axios.get(`${API_BASE}/api/files`, {
      params: { path: currentSessionPath.value }
    })

    if (res.data.files) {
      fileList.value = res.data.files.map((file: FileItem) => ({
        ...file,
        url: `${API_BASE}/api/download?path=${encodeURIComponent(file.path)}`
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
    const res = await axios.get(`${API_BASE}/api/ragflow/documents`, {
      params: { dataset_name_or_id: datasetId }
    })

    if (res.data.error) {
      showRagflowMessage(res.data.error, true)
      ragflowDocuments.value = []
      return
    }

    ragflowDocuments.value = res.data.documents ?? []
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
    const res = await axios.get(`${API_BASE}/api/ragflow/datasets`)

    if (res.data.error) {
      showRagflowMessage(res.data.error, true)
      ragflowDatasets.value = []
      ragflowDocuments.value = []
      return
    }

    ragflowDatasets.value = res.data.datasets ?? []
    const stillExists = ragflowDatasets.value.some((dataset) => dataset.id === selectedDatasetId.value)
    if (!stillExists) {
      selectedDatasetId.value = ragflowDatasets.value[0]?.id ?? ''
    }

    if (selectedDatasetId.value) {
      await fetchRagflowDocuments(selectedDatasetId.value)
    }
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

const triggerKbFileUpload = () => {
  kbFileInputRef.value?.click()
}

const handleKbFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  selectedKbFiles.value = [...selectedKbFiles.value, ...Array.from(target.files)]
  target.value = ''
}

const removeKbFile = (index: number) => {
  selectedKbFiles.value.splice(index, 1)
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

    const res = await axios.post(`${API_BASE}/api/ragflow/documents/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.data.error) {
      showRagflowMessage(res.data.error, true)
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
    const res = await axios.post(`${API_BASE}/api/ragflow/documents/parse`, {
      dataset_name_or_id: selectedDatasetId.value,
      document_names_or_ids: document.id
    })

    if (res.data.error) {
      showRagflowMessage(res.data.error, true)
      return
    }

    showRagflowMessage(`已提交解析：${document.name}`)
    await fetchRagflowDocuments()
  } catch (error: any) {
    showRagflowMessage(`解析文档失败：${error.message || '未知错误'}`, true)
  }
}

const deleteKnowledgeDocument = async (document: RagflowDocument) => {
  if (!selectedDatasetId.value) return
  if (!window.confirm(`确定删除文档“${document.name}”吗？`)) return

  try {
    showRagflowMessage('')
    const res = await axios.post(`${API_BASE}/api/ragflow/documents/delete`, {
      dataset_name_or_id: selectedDatasetId.value,
      document_names_or_ids: document.id
    })

    if (res.data.error) {
      showRagflowMessage(res.data.error, true)
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

  const lastAiMsg = [...messages.value].reverse().find((item) => item.role === 'ai')

  if (event === 'session_created') {
    currentSessionPath.value = eventData.path
    const parts = eventData.path.split(/output[\\/]/)
    if (parts.length > 1) {
      currentSessionUrl.value = `${API_BASE}/outputs/${parts[1].replace(/\\/g, '/')}`
    }
    isSidebarOpen.value = true
    fetchFiles()
  }

  if (event === 'tool_start') {
    fetchFiles()
    setTimeout(fetchFiles, 1800)

    if (lastAiMsg) {
      if (!lastAiMsg.logs) lastAiMsg.logs = []
      lastAiMsg.logs.push({
        type: 'tool',
        title: `使用工具：${eventData.tool_name}`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString()
      })

      if (eventData.args?.filename && currentSessionUrl.value) {
        if (!lastAiMsg.files) lastAiMsg.files = []
        const fileUrl = `${currentSessionUrl.value}/${eventData.args.filename}`
        if (!lastAiMsg.files.find((file) => file.name === eventData.args.filename)) {
          lastAiMsg.files.push({
            name: eventData.args.filename,
            path: eventData.args.filename,
            url: fileUrl
          })
        }
      }
    }
  }

  if (event === 'assistant_call') {
    fetchFiles()
    if (lastAiMsg) {
      if (!lastAiMsg.logs) lastAiMsg.logs = []
      lastAiMsg.logs.push({
        type: 'agent',
        title: `正在使用助手：${eventData.assistant_name}`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString()
      })
    }
  }

  if (event === 'task_result') {
    if (lastAiMsg) {
      lastAiMsg.content = eventData.result
    } else {
      messages.value.push({
        role: 'ai',
        content: eventData.result,
        timestamp: Date.now()
      })
    }
    status.value = 'idle'
    fetchFiles()
  }

  if (event === 'error') {
    messages.value.push({
      role: 'system',
      content: `Error: ${message}`,
      timestamp: Date.now()
    })
    status.value = 'idle'
  }

  scrollToBottom()
}

const connectWebSocket = () => {
  socket.value?.close()
  const ws = new WebSocket(`${WS_BASE}/ws/${currentThreadId.value}`)

  ws.onmessage = (event) => {
    try {
      handleSocketMessage(JSON.parse(event.data))
    } catch (error) {
      console.error('Error parsing WebSocket message', error)
    }
  }

  ws.onclose = () => {
    if (socket.value === ws) {
      setTimeout(connectWebSocket, 3000)
    }
  }

  socket.value = ws
}

const uploadSelectedFiles = async (lastAiMsg: Message) => {
  if (selectedFiles.value.length === 0) return

  if (!lastAiMsg.logs) lastAiMsg.logs = []
  lastAiMsg.logs.push({
    type: 'info',
    title: `上传文件：${selectedFiles.value.length} 个`,
    details: selectedFiles.value.map((file) => ({ name: file.name, size: file.size })),
    timestamp: new Date().toLocaleTimeString()
  })

  const formData = new FormData()
  formData.append('thread_id', currentThreadId.value)
  selectedFiles.value.forEach((file) => formData.append('files', file))

  await axios.post(`${API_BASE}/api/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })

  selectedFiles.value = []
  lastAiMsg.logs.push({
    type: 'success',
    title: '文件上传完成',
    details: null,
    timestamp: new Date().toLocaleTimeString()
  })
}

const sendMessage = async () => {
  if (!canSend.value) return

  const query = inputQuery.value.trim() || '请分析我上传的文件'
  inputQuery.value = ''
  status.value = 'running'

  messages.value.push({
    role: 'user',
    content: query,
    timestamp: Date.now()
  })

  const aiMessage: Message = {
    role: 'ai',
    content: '',
    logs: [],
    files: [],
    timestamp: Date.now()
  }
  messages.value.push(aiMessage)
  scrollToBottom()

  try {
    await uploadSelectedFiles(aiMessage)

    const res = await axios.post(`${API_BASE}/api/task`, {
      query,
      thread_id: currentThreadId.value
    })

    if (res.data?.thread_id) {
      currentThreadId.value = res.data.thread_id
    }
  } catch (error: any) {
    messages.value.push({
      role: 'system',
      content: `请求失败：${error.message || '未知错误'}`,
      timestamp: Date.now()
    })
    status.value = 'idle'
  }
}

const triggerFileUpload = () => {
  fileInputRef.value?.click()
}

const handleFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
  target.value = ''
}

const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1)
}

const useStarterPrompt = (prompt: string) => {
  inputQuery.value = prompt
}

const startNewChat = () => {
  currentThreadId.value = crypto.randomUUID()
  localStorage.setItem('deep-agent-thread-id', currentThreadId.value)
  messages.value = []
  fileList.value = []
  selectedFiles.value = []
  currentSessionPath.value = ''
  currentSessionUrl.value = ''
  status.value = 'idle'
  connectWebSocket()
}

const renderMarkdown = (text: string) => {
  if (!text) return '<span class="thinking-text">正在分析任务...</span>'
  return marked.parse(text)
}

onMounted(() => {
  isSidebarOpen.value = window.innerWidth > 1120
  connectWebSocket()
})
</script>

<template>
  <div class="app-shell" :class="{ 'drawer-visible': isSidebarOpen }">
    <aside class="workspace-rail">
      <div class="brand-lockup">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2.5 15.2 9l6.8 3-6.8 3L12 21.5 8.8 15 2 12l6.8-3L12 2.5Z" />
          </svg>
        </div>
        <div>
          <p>Deep Agent</p>
          <strong>多智能体深度搜索</strong>
        </div>
      </div>

      <div class="status-board">
        <div class="status-row">
          <span>运行状态</span>
          <strong :class="status">{{ status === 'running' ? '执行中' : '待命' }}</strong>
        </div>
        <div class="status-row">
          <span>会话</span>
          <strong>{{ currentThreadId.slice(0, 8) }}</strong>
        </div>
        <div class="status-row">
          <span>文件</span>
          <strong>{{ fileList.length }}</strong>
        </div>
      </div>

      <div class="activity-panel">
        <div class="panel-title">最近动作</div>
        <div v-if="latestLogs.length === 0" class="empty-state">等待任务开始</div>
        <div v-else class="activity-list">
          <div v-for="(log, index) in latestLogs" :key="`${log.timestamp}-${index}`" class="activity-item">
            <span class="activity-dot" :class="log.type"></span>
            <div>
              <strong>{{ normalizeTitle(log.title) }}</strong>
              <time>{{ log.timestamp }}</time>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <main class="conversation-pane">
      <header class="topbar">
        <div>
          <span class="eyebrow">Agent Console</span>
          <h1>把问题、知识库和文件串起来</h1>
        </div>
        <div class="topbar-actions">
          <button class="files-toggle" type="button" @click="openFilesDrawer">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h4l2 2h5A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-11Z" />
            </svg>
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
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            新会话
          </button>
        </div>
      </header>

      <section v-if="isWelcomeScreen" class="welcome-panel">
        <div class="welcome-copy">
          <span class="eyebrow">Ready</span>
          <h2>今天要让哪个助手开工？</h2>
          <p>可以查数据库、检索 RAGFlow、上传资料，也可以把结果整理成文档。</p>
        </div>
        <div class="prompt-grid">
          <button v-for="prompt in starterPrompts" :key="prompt" type="button" @click="useStarterPrompt(prompt)">
            {{ prompt }}
          </button>
        </div>
      </section>

      <section v-else class="chat-scroll-area">
        <div class="chat-list">
          <article v-for="(msg, index) in messages" :key="index" class="message" :class="msg.role">
            <div v-if="msg.role === 'user'" class="message-bubble user-bubble">
              <time>{{ formatTime(msg.timestamp) }}</time>
              <p>{{ msg.content }}</p>
            </div>

            <div v-else-if="msg.role === 'ai'" class="assistant-message">
              <div class="assistant-avatar">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 3 14.9 9.1 21 12l-6.1 2.9L12 21l-2.9-6.1L3 12l6.1-2.9L12 3Z" />
                </svg>
              </div>
              <div class="assistant-body">
                <details v-if="msg.logs?.length" class="process-card" open>
                  <summary>
                    <span class="run-pulse" v-if="status === 'running' && index === messages.length - 1"></span>
                    执行过程
                  </summary>
                  <div class="process-list">
                    <div v-for="(log, logIndex) in msg.logs" :key="logIndex" class="process-item" :class="log.type">
                      <div class="process-heading">
                        <span>{{ normalizeTitle(log.title) }}</span>
                        <time>{{ log.timestamp }}</time>
                      </div>
                      <pre v-if="log.details">{{ JSON.stringify(log.details, null, 2) }}</pre>
                    </div>
                  </div>
                </details>

                <div class="message-bubble ai-bubble markdown-body" v-html="renderMarkdown(msg.content)"></div>

                <div v-if="msg.files?.length" class="result-files">
                  <a v-for="file in msg.files" :key="file.name" :href="file.url" target="_blank" :download="file.name">
                    <span>{{ getFileTag(file.name) }}</span>
                    <strong>{{ file.name }}</strong>
                  </a>
                </div>
              </div>
            </div>

            <div v-else class="system-message">
              {{ msg.content }}
            </div>
          </article>
          <div ref="messagesEndRef" class="scroll-anchor"></div>
        </div>
      </section>

      <footer class="composer-area">
        <div v-if="selectedFiles.length" class="selected-files">
          <div v-for="(file, index) in selectedFiles" :key="`${file.name}-${index}`" class="selected-file">
            <span>{{ getFileTag(file.name) }}</span>
            <strong>{{ file.name }}</strong>
            <button type="button" @click="removeFile(index)" aria-label="移除文件">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m6 6 12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
        </div>

        <div class="composer">
          <input ref="fileInputRef" type="file" multiple @change="handleFileChange" />
          <button class="icon-button" type="button" :disabled="status === 'running'" @click="triggerFileUpload" aria-label="上传文件">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v10m0-10 4 4m-4-4-4 4M5 19h14" />
            </svg>
          </button>
          <textarea
            v-model="inputQuery"
            :disabled="status === 'running'"
            placeholder="输入任务..."
            rows="1"
            @keydown.enter.exact.prevent="sendMessage"
          ></textarea>
          <button class="send-button" type="button" :disabled="!canSend" @click="sendMessage" aria-label="发送">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m4 12 15-7-4 14-3-6-8-1Z" />
            </svg>
          </button>
        </div>
      </footer>
    </main>

    <aside v-if="isSidebarOpen" class="files-drawer open">
      <div class="drawer-header">
        <div>
          <span class="eyebrow">{{ drawerMode === 'knowledge' ? 'RAGFlow' : 'Workspace' }}</span>
          <h2>{{ drawerMode === 'knowledge' ? '知识库管理' : '会话文件' }}</h2>
        </div>
        <div class="drawer-actions">
          <button
            type="button"
            @click="drawerMode === 'knowledge' ? fetchRagflowDatasets() : fetchFiles()"
            :aria-label="drawerMode === 'knowledge' ? '刷新知识库' : '刷新文件'"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v6h-6" />
            </svg>
          </button>
          <button type="button" @click="isSidebarOpen = false" aria-label="关闭文件栏">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6 18 18M18 6 6 18" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="drawerMode === 'files'" class="drawer-section">
        <div v-if="!fileList.length" class="drawer-empty">
          <div class="mini-illustration"></div>
          <p>还没有生成文件</p>
        </div>

        <div v-else class="drawer-files">
          <a v-for="file in fileList" :key="file.path" :href="file.url" target="_blank" :download="file.name" class="drawer-file">
            <span class="file-tag">{{ getFileTag(file.name) }}</span>
            <div>
              <strong>{{ file.name }}</strong>
              <small>{{ formatBytes(file.size) }}</small>
            </div>
          </a>
        </div>
      </div>

      <div v-else class="knowledge-manager">
        <div v-if="ragflowError" class="inline-alert error">{{ ragflowError }}</div>
        <div v-if="ragflowMessage" class="inline-alert success">{{ ragflowMessage }}</div>

        <div v-if="ragflowLoading && !ragflowDatasets.length" class="drawer-empty compact">
          <p>正在读取 RAGFlow 知识库...</p>
        </div>

        <div v-else-if="!ragflowDatasets.length" class="drawer-empty compact">
          <div class="mini-illustration"></div>
          <p>当前没有知识库</p>
        </div>

        <template v-else>
          <div class="dataset-list">
            <button
              v-for="dataset in ragflowDatasets"
              :key="dataset.id"
              type="button"
              class="dataset-card"
              :class="{ active: selectedDatasetId === dataset.id }"
              @click="selectRagflowDataset(dataset)"
            >
              <span>{{ dataset.name.slice(0, 1) }}</span>
              <div>
                <strong>{{ dataset.name }}</strong>
                <small>{{ dataset.doc_num ?? 0 }} 个文档 · {{ dataset.chunk_num ?? 0 }} 个切片</small>
              </div>
            </button>
          </div>

          <section class="kb-upload-panel">
            <div>
              <strong>上传到 {{ selectedDataset?.name || '知识库' }}</strong>
              <small>上传后会自动提交解析</small>
            </div>
            <input ref="kbFileInputRef" type="file" multiple @change="handleKbFileChange" />
            <button class="kb-pick-button" type="button" :disabled="ragflowUploading" @click="triggerKbFileUpload">
              选择文件
            </button>

            <div v-if="selectedKbFiles.length" class="kb-selected-files">
              <div v-for="(file, index) in selectedKbFiles" :key="`${file.name}-${index}`" class="kb-selected-file">
                <span>{{ getFileTag(file.name) }}</span>
                <strong>{{ file.name }}</strong>
                <button type="button" @click="removeKbFile(index)" aria-label="移除知识库上传文件">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 6 18 18M18 6 6 18" />
                  </svg>
                </button>
              </div>
            </div>

            <button
              class="kb-upload-button"
              type="button"
              :disabled="!selectedDatasetId || !selectedKbFiles.length || ragflowUploading"
              @click="uploadKnowledgeFiles"
            >
              {{ ragflowUploading ? '上传中...' : '上传并解析' }}
            </button>
          </section>

          <section class="document-panel">
            <div class="document-panel-title">
              <strong>文档列表</strong>
              <small>{{ ragflowDocuments.length }} 个</small>
            </div>

            <div v-if="!ragflowDocuments.length" class="drawer-empty compact">
              <p>这个知识库还没有文档</p>
            </div>

            <div v-else class="document-list">
              <article v-for="document in ragflowDocuments" :key="document.id" class="document-card">
                <div class="document-main">
                  <span class="file-tag">{{ getFileTag(document.name) }}</span>
                  <div>
                    <strong>{{ document.name }}</strong>
                    <small>
                      状态: {{ document.run ?? '未知' }}
                      <template v-if="document.chunk_count !== null && document.chunk_count !== undefined">
                        · {{ document.chunk_count }} 切片
                      </template>
                    </small>
                  </div>
                </div>
                <div class="document-actions">
                  <button type="button" @click="parseKnowledgeDocument(document)">解析</button>
                  <button type="button" class="danger" @click="deleteKnowledgeDocument(document)">删除</button>
                </div>
              </article>
            </div>
          </section>
        </template>
      </div>
    </aside>
  </div>
</template>

<style>
:root {
  --page: #f5f1e8;
  --ink: #1e2329;
  --muted: #69717d;
  --line: #ded7c9;
  --panel: #fffaf1;
  --panel-strong: #ffffff;
  --teal: #087f8c;
  --green: #4f7d48;
  --coral: #d85c45;
  --yellow: #f1b84b;
  --blue: #3f6eb3;
  --shadow: 0 18px 50px rgba(63, 52, 35, 0.12);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font-family: Inter, "Microsoft YaHei", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

button,
textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
}

.app-shell {
  width: 100vw;
  height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  background:
    linear-gradient(90deg, rgba(8, 127, 140, 0.08) 1px, transparent 1px),
    linear-gradient(0deg, rgba(216, 92, 69, 0.06) 1px, transparent 1px),
    var(--page);
  background-size: 42px 42px;
  overflow: hidden;
}

.app-shell.drawer-visible {
  grid-template-columns: 280px minmax(0, 1fr) 320px;
}

.workspace-rail,
.files-drawer {
  background: rgba(255, 250, 241, 0.82);
  border-color: var(--line);
  border-style: solid;
  backdrop-filter: blur(16px);
}

.workspace-rail {
  border-width: 0 1px 0 0;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.brand-lockup {
  display: flex;
  gap: 12px;
  align-items: center;
}

.brand-mark,
.assistant-avatar {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
}

.brand-mark {
  width: 42px;
  height: 42px;
  background: var(--ink);
  color: var(--yellow);
  border-radius: 8px;
  box-shadow: 6px 6px 0 rgba(216, 92, 69, 0.22);
}

.brand-mark svg,
.assistant-avatar svg,
.files-toggle svg,
.icon-button svg,
.send-button svg,
.drawer-header button svg,
.selected-file button svg,
.kb-selected-file button svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.brand-mark svg,
.assistant-avatar svg {
  fill: currentColor;
  stroke: none;
}

.brand-lockup p,
.eyebrow {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.brand-lockup strong {
  display: block;
  margin-top: 2px;
  font-size: 15px;
}

.status-board,
.activity-panel,
.welcome-panel,
.process-card,
.message-bubble,
.composer,
.selected-file,
.drawer-file,
.dataset-card,
.kb-upload-panel,
.document-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.status-board {
  padding: 14px;
  display: grid;
  gap: 12px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 13px;
}

.status-row strong {
  color: var(--ink);
}

.status-row strong.running {
  color: var(--coral);
}

.status-row strong.idle {
  color: var(--green);
}

.activity-panel {
  min-height: 220px;
  padding: 14px;
  box-shadow: none;
}

.panel-title {
  font-size: 13px;
  font-weight: 800;
  margin-bottom: 12px;
}

.empty-state,
.drawer-empty {
  color: var(--muted);
  font-size: 14px;
}

.activity-list {
  display: grid;
  gap: 12px;
}

.activity-item {
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 10px;
  align-items: start;
}

.activity-dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--blue);
}

.activity-dot.tool {
  background: var(--teal);
}

.activity-dot.agent {
  background: var(--coral);
}

.activity-item strong {
  display: block;
  font-size: 12px;
  line-height: 1.45;
}

.activity-item time {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-top: 2px;
}

.conversation-pane {
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: 100vh;
}

.topbar {
  padding: 22px 28px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.topbar h1 {
  margin: 2px 0 0;
  font-size: clamp(22px, 3vw, 34px);
  line-height: 1.15;
}

.files-toggle,
.new-chat-button,
.drawer-header button,
.icon-button,
.send-button,
.selected-file button,
.kb-pick-button,
.kb-upload-button,
.kb-selected-file button,
.document-actions button {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-strong);
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
}

.files-toggle,
.new-chat-button {
  gap: 8px;
  min-height: 40px;
  padding: 0 14px;
  font-weight: 800;
  white-space: nowrap;
}

.new-chat-button {
  background: var(--ink);
  color: white;
  border-color: var(--ink);
}

.knowledge-toggle {
  background: #e3f1ed;
  border-color: #bddbd5;
}

.new-chat-button:disabled {
  opacity: 0.5;
}

.welcome-panel {
  align-self: center;
  margin: 0 28px 18px;
  padding: clamp(22px, 4vw, 42px);
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(260px, 0.9fr);
  gap: 28px;
  background:
    linear-gradient(135deg, rgba(8, 127, 140, 0.14), transparent 44%),
    linear-gradient(315deg, rgba(241, 184, 75, 0.22), transparent 46%),
    var(--panel);
}

.welcome-copy h2 {
  margin: 6px 0 12px;
  font-size: clamp(34px, 6vw, 68px);
  line-height: 0.96;
  max-width: 680px;
}

.welcome-copy p {
  max-width: 520px;
  margin: 0;
  color: var(--muted);
  font-size: 16px;
}

.prompt-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  align-content: end;
}

.prompt-grid button {
  min-height: 78px;
  padding: 14px;
  text-align: left;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--line);
  border-radius: 8px;
  font-weight: 800;
}

.prompt-grid button:hover,
.files-toggle:hover,
.new-chat-button:hover:not(:disabled),
.icon-button:hover,
.drawer-header button:hover,
.selected-file button:hover {
  border-color: var(--teal);
  transform: translateY(-1px);
}

.chat-scroll-area {
  overflow-y: auto;
  padding: 0 28px 16px;
}

.chat-list {
  width: min(900px, 100%);
  margin: 0 auto;
  display: grid;
  gap: 18px;
  padding: 8px 0 28px;
}

.message {
  min-width: 0;
}

.message.user {
  display: flex;
  justify-content: flex-end;
}

.assistant-message {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
}

.assistant-avatar {
  width: 38px;
  height: 38px;
  margin-top: 4px;
  border-radius: 8px;
  color: var(--teal);
  background: #dff0ec;
  border: 1px solid #bddbd5;
}

.assistant-body {
  min-width: 0;
  display: grid;
  gap: 10px;
}

.message-bubble {
  padding: 14px 16px;
  box-shadow: none;
}

.user-bubble {
  width: fit-content;
  max-width: min(680px, 86%);
  background: var(--ink);
  color: white;
  border-color: var(--ink);
}

.user-bubble time {
  display: block;
  color: rgba(255, 255, 255, 0.62);
  font-size: 11px;
  margin-bottom: 4px;
}

.user-bubble p {
  margin: 0;
  white-space: pre-wrap;
}

.ai-bubble {
  background: rgba(255, 250, 241, 0.86);
}

.markdown-body {
  line-height: 1.7;
}

.markdown-body p:first-child {
  margin-top: 0;
}

.markdown-body p:last-child {
  margin-bottom: 0;
}

.markdown-body pre {
  overflow-x: auto;
  padding: 12px;
  border-radius: 8px;
  background: #222831;
  color: #f7f0df;
}

.markdown-body code {
  font-family: "Cascadia Code", Consolas, monospace;
}

.thinking-text {
  color: var(--muted);
}

.process-card {
  padding: 10px 12px;
  background: #fdf5df;
  box-shadow: none;
}

.process-card summary {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 800;
  color: var(--ink);
  list-style: none;
}

.process-card summary::-webkit-details-marker {
  display: none;
}

.run-pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--coral);
  box-shadow: 0 0 0 0 rgba(216, 92, 69, 0.42);
  animation: pulse 1.4s infinite;
}

.process-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.process-item {
  border-left: 3px solid var(--blue);
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.62);
  border-radius: 0 8px 8px 0;
}

.process-item.tool {
  border-left-color: var(--teal);
}

.process-item.agent {
  border-left-color: var(--coral);
}

.process-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  font-weight: 800;
}

.process-heading time {
  flex: 0 0 auto;
  color: var(--muted);
  font-weight: 600;
}

.process-item pre {
  margin: 8px 0 0;
  max-height: 240px;
  overflow: auto;
  border-radius: 8px;
  padding: 10px;
  background: #251f1a;
  color: #f8efe1;
  font-size: 12px;
}

.result-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.result-files a,
.drawer-file {
  text-decoration: none;
  color: var(--ink);
}

.result-files a {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-strong);
}

.result-files span,
.file-tag,
.selected-file span {
  min-width: 40px;
  padding: 4px 6px;
  border-radius: 6px;
  background: #e3f1ed;
  color: var(--teal);
  font-size: 11px;
  font-weight: 900;
  text-align: center;
}

.system-message {
  width: min(720px, 100%);
  margin: 0 auto;
  padding: 12px 14px;
  color: #7b3027;
  background: #ffe8df;
  border: 1px solid #efb7aa;
  border-radius: 8px;
}

.scroll-anchor {
  height: 16px;
}

.composer-area {
  padding: 10px 28px 22px;
}

.selected-files {
  width: min(900px, 100%);
  margin: 0 auto 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.selected-file {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 320px;
  padding: 8px;
  box-shadow: none;
}

.selected-file strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.selected-file button {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
}

.composer {
  width: min(900px, 100%);
  margin: 0 auto;
  min-height: 62px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 46px;
  gap: 10px;
  align-items: center;
  padding: 9px;
  background: rgba(255, 255, 255, 0.82);
}

.composer input[type="file"] {
  display: none;
}

.icon-button,
.send-button {
  width: 42px;
  height: 42px;
}

.send-button {
  color: white;
  background: var(--teal);
  border-color: var(--teal);
}

.send-button:disabled {
  color: #9aa0a6;
  background: #edf0ee;
  border-color: #d7dcd8;
}

.composer textarea {
  width: 100%;
  min-height: 38px;
  max-height: 140px;
  resize: vertical;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
  padding: 9px 2px;
  font-size: 15px;
}

.files-drawer {
  border-width: 0 0 0 1px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.drawer-header h2 {
  margin: 2px 0 0;
  font-size: 20px;
}

.drawer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-header button {
  width: 38px;
  height: 38px;
}

.drawer-empty {
  display: grid;
  place-items: center;
  gap: 12px;
  min-height: 240px;
  border: 1px dashed var(--line);
  border-radius: 8px;
}

.drawer-empty.compact {
  min-height: 120px;
  padding: 18px;
}

.mini-illustration {
  width: 74px;
  height: 92px;
  border-radius: 8px;
  background:
    linear-gradient(var(--teal), var(--teal)) 16px 22px / 42px 4px no-repeat,
    linear-gradient(var(--yellow), var(--yellow)) 16px 38px / 34px 4px no-repeat,
    linear-gradient(var(--coral), var(--coral)) 16px 54px / 26px 4px no-repeat,
    #fff;
  border: 2px solid var(--ink);
  box-shadow: 8px 8px 0 rgba(8, 127, 140, 0.18);
}

.drawer-files {
  overflow-y: auto;
  display: grid;
  gap: 10px;
  padding-right: 4px;
}

.drawer-section,
.knowledge-manager {
  min-height: 0;
  overflow-y: auto;
  display: grid;
  gap: 14px;
  padding-right: 4px;
}

.drawer-file {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px;
  box-shadow: none;
}

.drawer-file strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.drawer-file small {
  color: var(--muted);
}

.inline-alert {
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.inline-alert.error {
  color: #7b3027;
  background: #ffe8df;
  border: 1px solid #efb7aa;
}

.inline-alert.success {
  color: #315b31;
  background: #e8f2e4;
  border: 1px solid #bed8b8;
}

.dataset-list {
  display: grid;
  gap: 10px;
}

.dataset-card {
  width: 100%;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px;
  text-align: left;
  box-shadow: none;
}

.dataset-card.active {
  border-color: var(--teal);
  background: #edf8f4;
}

.dataset-card > span {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--ink);
  color: white;
  font-weight: 900;
}

.dataset-card strong,
.document-card strong,
.kb-selected-file strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dataset-card small,
.document-card small,
.kb-upload-panel small {
  display: block;
  color: var(--muted);
  margin-top: 3px;
}

.kb-upload-panel {
  display: grid;
  gap: 10px;
  padding: 12px;
  box-shadow: none;
}

.kb-upload-panel input[type="file"] {
  display: none;
}

.kb-pick-button,
.kb-upload-button {
  min-height: 38px;
  padding: 0 12px;
  font-weight: 800;
}

.kb-upload-button {
  color: white;
  background: var(--teal);
  border-color: var(--teal);
}

.kb-upload-button:disabled,
.kb-pick-button:disabled {
  color: #9aa0a6;
  background: #edf0ee;
  border-color: #d7dcd8;
}

.kb-selected-files {
  display: grid;
  gap: 8px;
}

.kb-selected-file {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 30px;
  gap: 8px;
  align-items: center;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.68);
}

.kb-selected-file button {
  width: 30px;
  height: 30px;
}

.document-panel {
  display: grid;
  gap: 10px;
}

.document-panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.document-panel-title small {
  color: var(--muted);
}

.document-list {
  display: grid;
  gap: 10px;
}

.document-card {
  display: grid;
  gap: 10px;
  padding: 10px;
  box-shadow: none;
}

.document-main {
  min-width: 0;
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.document-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.document-actions button {
  min-height: 34px;
  font-size: 13px;
  font-weight: 800;
}

.document-actions button.danger {
  color: #7b3027;
  background: #ffe8df;
  border-color: #efb7aa;
}

@keyframes pulse {
  70% {
    box-shadow: 0 0 0 9px rgba(216, 92, 69, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(216, 92, 69, 0);
  }
}

@media (max-width: 1120px) {
  .app-shell {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .app-shell.drawer-visible {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .files-drawer {
    position: fixed;
    inset: 0 0 0 auto;
    width: min(360px, 92vw);
    z-index: 20;
    transform: translateX(104%);
    transition: transform 0.2s ease;
  }

  .files-drawer.open {
    transform: translateX(0);
  }
}

@media (max-width: 780px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .app-shell.drawer-visible {
    grid-template-columns: 1fr;
  }

  .workspace-rail {
    display: none;
  }

  .topbar {
    padding: 16px 16px 8px;
    align-items: flex-start;
  }

  .topbar-actions {
    flex-direction: column;
    gap: 8px;
  }

  .files-toggle,
  .new-chat-button {
    min-width: 82px;
    padding: 0 10px;
  }

  .welcome-panel {
    grid-template-columns: 1fr;
    margin: 0 16px;
  }

  .prompt-grid {
    grid-template-columns: 1fr;
  }

  .chat-scroll-area,
  .composer-area {
    padding-left: 16px;
    padding-right: 16px;
  }

  .assistant-message {
    grid-template-columns: 1fr;
  }

  .assistant-avatar {
    display: none;
  }
}
</style>
