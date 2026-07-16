<script setup lang="ts">
import { computed, ref } from 'vue'

import type { RagflowDataset, RagflowDocument } from '../types'
import { getFileTag } from '../utils/formatters'

const props = defineProps<{
  datasets: RagflowDataset[]
  documents: RagflowDocument[]
  selectedDataset?: RagflowDataset
  selectedDatasetId: string
  selectedFiles: File[]
  loading: boolean
  uploading: boolean
  creating: boolean
  parsingDocumentId: string
  message: string
  error: string
  newDatasetName: string
  newDatasetDescription: string
}>()

const emit = defineEmits<{
  back: []
  refresh: []
  create: []
  'update:newDatasetName': [value: string]
  'update:newDatasetDescription': [value: string]
  select: [dataset: RagflowDataset]
  'file-change': [event: Event]
  'remove-file': [index: number]
  upload: []
  parse: [document: RagflowDocument]
  delete: [document: RagflowDocument]
}>()

const showCreateDialog = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const currentDocumentCount = computed(() => props.documents.length)
const currentChunkCount = computed(() => props.documents.reduce(
  (total, document) => total + Number(document.chunk_count ?? 0),
  0,
))

const totalDocuments = computed(() => props.datasets.reduce(
  (total, dataset) => total + (dataset.id === props.selectedDatasetId
    ? currentDocumentCount.value
    : Number(dataset.doc_num ?? 0)),
  0,
))

const totalChunks = computed(() => props.datasets.reduce(
  (total, dataset) => total + (dataset.id === props.selectedDatasetId
    ? currentChunkCount.value
    : Number(dataset.chunk_num ?? 0)),
  0,
))

const documentStatus = (document: RagflowDocument) => {
  const raw = String(document.run ?? '').trim().toUpperCase()
  if (['DONE', 'SUCCESS'].includes(raw)) return { label: '已完成', tone: 'success' }
  if (['FAILED', 'ERROR'].includes(raw)) return { label: '失败', tone: 'danger' }
  if (['CANCEL', 'CANCELED', 'CANCELLED'].includes(raw)) return { label: '已取消', tone: 'muted' }
  if (['PENDING', 'RUNNING', 'PARSE', 'PROCESSING', '1'].includes(raw)) return { label: '解析中', tone: 'warning' }
  return { label: raw || '待解析', tone: 'muted' }
}

const displayDocumentStatus = (document: RagflowDocument) => (
  props.parsingDocumentId === document.id
    ? { label: '已提交解析', tone: 'warning' }
    : documentStatus(document)
)

const documentProgress = (document: RagflowDocument) => {
  if (props.parsingDocumentId === document.id) return '--'
  const status = documentStatus(document)
  if (status.tone === 'success') return '100%'
  if (status.tone === 'muted') return '0%'

  const value = Number(document.progress)
  return Number.isFinite(value) ? `${Math.round(value)}%` : '--'
}

const submitCreate = () => {
  emit('create')
  showCreateDialog.value = false
}
</script>

<template>
  <section class="knowledge-workbench">
    <header class="knowledge-workbench-header">
      <div>
        <div class="knowledge-kicker">
          <span class="knowledge-live-dot"></span>
          RAGFlow 知识库
        </div>
        <h1>知识库工作台</h1>
        <p>管理可供 Agent 检索的文档，并跟踪解析和切片状态。</p>
      </div>
      <div class="knowledge-header-actions">
        <button type="button" class="knowledge-button ghost" :disabled="loading" @click="emit('refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5.3M20 4v7h-7" /></svg>
          刷新
        </button>
        <button type="button" class="knowledge-button dark" @click="showCreateDialog = true">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          新建知识库
        </button>
        <button type="button" class="knowledge-icon-button" title="返回对话" aria-label="返回对话" @click="emit('back')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6M8 12h12" /></svg>
        </button>
      </div>
    </header>

    <div v-if="error" class="knowledge-alert danger" role="alert">{{ error }}</div>
    <div v-else-if="message" class="knowledge-alert success">{{ message }}</div>

    <div class="knowledge-summary" aria-label="知识库概览">
      <div><span>知识库</span><strong>{{ datasets.length }}</strong></div>
      <div><span>文档</span><strong>{{ totalDocuments }}</strong></div>
      <div><span>切片</span><strong>{{ totalChunks }}</strong></div>
      <div class="summary-note"><span class="knowledge-live-dot"></span>已连接 RAGFlow</div>
    </div>

    <main class="knowledge-workspace">
      <aside class="knowledge-library-panel">
        <div class="knowledge-panel-heading">
          <div>
            <span>知识库列表</span>
            <small>{{ datasets.length }} 个空间</small>
          </div>
          <button type="button" class="knowledge-icon-button compact" title="新建知识库" aria-label="新建知识库" @click="showCreateDialog = true">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>

        <div v-if="loading && !datasets.length" class="knowledge-empty-state">正在读取知识库...</div>
        <div v-else-if="!datasets.length" class="knowledge-empty-state">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H10l2 2h5.5A2.5 2.5 0 0 1 20 7.5v10a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5zM8 12h8" /></svg>
          <strong>还没有知识库</strong>
          <span>先创建一个空间再上传资料</span>
        </div>
        <nav v-else class="knowledge-dataset-list">
          <button
            v-for="dataset in datasets"
            :key="dataset.id"
            type="button"
            class="knowledge-dataset-item"
            :class="{ active: selectedDatasetId === dataset.id }"
            @click="emit('select', dataset)"
          >
            <span class="knowledge-dataset-mark">{{ dataset.name.slice(0, 1) }}</span>
            <span class="knowledge-dataset-copy">
              <strong>{{ dataset.name }}</strong>
              <small>{{ dataset.id === selectedDatasetId ? currentDocumentCount : (dataset.doc_num ?? 0) }} 文档 · {{ dataset.id === selectedDatasetId ? currentChunkCount : (dataset.chunk_num ?? 0) }} 切片</small>
            </span>
            <svg class="dataset-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
          </button>
        </nav>
      </aside>

      <section class="knowledge-detail-panel">
        <template v-if="selectedDataset">
          <header class="selected-dataset-header">
            <div class="selected-dataset-title">
              <span class="knowledge-dataset-mark large">{{ selectedDataset.name.slice(0, 1) }}</span>
              <div>
                <span class="detail-overline">当前知识库</span>
                <h2>{{ selectedDataset.name }}</h2>
                <p>{{ selectedDataset.description || '暂未填写知识库说明' }}</p>
              </div>
            </div>
            <div class="selected-dataset-stats">
              <span><strong>{{ currentDocumentCount }}</strong>文档</span>
              <span><strong>{{ currentChunkCount }}</strong>切片</span>
            </div>
          </header>

          <section class="knowledge-upload-card">
            <div class="upload-card-copy">
              <span class="upload-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L8 8m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" /></svg></span>
              <div>
                <strong>添加资料</strong>
                <p>支持 PDF、DOCX、TXT 等文件，上传后会提交解析。</p>
              </div>
            </div>
            <div class="upload-card-actions">
              <input ref="fileInputRef" type="file" multiple @change="emit('file-change', $event)" />
              <button type="button" class="knowledge-button ghost" :disabled="uploading" @click="fileInputRef?.click()">选择文件</button>
              <button type="button" class="knowledge-button dark" :disabled="!selectedFiles.length || uploading" @click="emit('upload')">
                {{ uploading ? '上传中...' : `上传并解析${selectedFiles.length ? ` (${selectedFiles.length})` : ''}` }}
              </button>
            </div>
          </section>

          <div v-if="selectedFiles.length" class="upload-queue">
            <div v-for="(file, index) in selectedFiles" :key="`${file.name}-${index}`" class="upload-queue-item">
              <span class="file-type-badge">{{ getFileTag(file.name) }}</span>
              <strong>{{ file.name }}</strong>
              <small>{{ Math.max(1, Math.ceil(file.size / 1024)) }} KB</small>
              <button type="button" title="移除文件" :aria-label="`移除 ${file.name}`" @click="emit('remove-file', index)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" /></svg>
              </button>
            </div>
          </div>

          <section class="knowledge-document-section">
            <div class="knowledge-panel-heading document-heading">
              <div>
                <span>文档</span>
                <small>{{ documents.length }} 个文件</small>
              </div>
              <span v-if="loading" class="document-loading">正在同步...</span>
            </div>

            <div v-if="loading && !documents.length" class="knowledge-empty-state documents">正在读取文档...</div>
            <div v-else-if="!documents.length" class="knowledge-empty-state documents">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm7 0v5h5" /></svg>
              <strong>这个知识库还没有文档</strong>
              <span>从上方选择文件后上传解析</span>
            </div>
            <div v-else class="knowledge-document-table-wrap">
              <table class="knowledge-document-table">
                <thead>
                  <tr><th>文档</th><th>状态</th><th>进度</th><th>切片</th><th>Token</th><th><span class="sr-only">操作</span></th></tr>
                </thead>
                <tbody>
                  <tr v-for="document in documents" :key="document.id">
                    <td>
                      <div class="document-name-cell">
                        <span class="file-type-badge">{{ getFileTag(document.name) }}</span>
                        <div><strong>{{ document.name }}</strong><small>{{ document.update_date || document.create_date || '暂无更新时间' }}</small></div>
                      </div>
                    </td>
                    <td><span class="document-status" :class="displayDocumentStatus(document).tone"><i></i>{{ displayDocumentStatus(document).label }}</span></td>
                    <td>{{ documentProgress(document) }}</td>
                    <td>{{ document.chunk_count ?? '--' }}</td>
                    <td>{{ document.token_count ?? '--' }}</td>
                    <td>
                      <div class="document-row-actions">
                        <button type="button" title="重新解析" :aria-label="`解析 ${document.name}`" @click="emit('parse', document)">
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5.3M20 4v7h-7" /></svg>
                        </button>
                        <button type="button" class="danger" title="删除文档" :aria-label="`删除 ${document.name}`" @click="emit('delete', document)">
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13" /></svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>

        <div v-else class="knowledge-no-selection">
          <span class="knowledge-dataset-mark large">?</span>
          <h2>选择一个知识库</h2>
          <p>选择后即可上传文档、查看解析状态和管理资料。</p>
          <button type="button" class="knowledge-button dark" @click="showCreateDialog = true">新建第一个知识库</button>
        </div>
      </section>
    </main>

    <div v-if="showCreateDialog" class="knowledge-modal-backdrop" @click.self="showCreateDialog = false">
      <form class="knowledge-modal" @submit.prevent="submitCreate">
        <div class="knowledge-modal-header">
          <div><span class="detail-overline">RAGFlow</span><h2>新建知识库</h2></div>
          <button type="button" class="knowledge-icon-button compact" title="关闭" aria-label="关闭" @click="showCreateDialog = false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" /></svg></button>
        </div>
        <label><span>知识库名称</span><input :value="newDatasetName" maxlength="128" required autofocus placeholder="例如：产品资料库" @input="emit('update:newDatasetName', ($event.target as HTMLInputElement).value)" /></label>
        <label><span>说明 <small>可选</small></span><textarea :value="newDatasetDescription" maxlength="1000" rows="4" placeholder="简要说明知识库中存储的资料" @input="emit('update:newDatasetDescription', ($event.target as HTMLTextAreaElement).value)"></textarea></label>
        <div class="knowledge-modal-actions"><button type="button" class="knowledge-button ghost" @click="showCreateDialog = false">取消</button><button type="submit" class="knowledge-button dark" :disabled="creating">{{ creating ? '创建中...' : '创建知识库' }}</button></div>
      </form>
    </div>
  </section>
</template>
