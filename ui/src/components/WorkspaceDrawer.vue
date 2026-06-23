<script setup lang="ts">
import type { DrawerMode, FileItem, RagflowDataset, RagflowDocument } from '../types'
import KnowledgeBaseManager from './KnowledgeBaseManager.vue'
import SessionFiles from './SessionFiles.vue'

defineProps<{
  mode: DrawerMode
  files: FileItem[]
  datasets: RagflowDataset[]
  documents: RagflowDocument[]
  selectedDataset?: RagflowDataset
  selectedDatasetId: string
  selectedKbFiles: File[]
  ragflowLoading: boolean
  ragflowUploading: boolean
  ragflowMessage: string
  ragflowError: string
}>()

const emit = defineEmits<{
  close: []
  refresh: []
  'download-file': [file: FileItem]
  'select-dataset': [dataset: RagflowDataset]
  'kb-file-change': [event: Event]
  'remove-kb-file': [index: number]
  'upload-kb-files': []
  'parse-document': [document: RagflowDocument]
  'delete-document': [document: RagflowDocument]
}>()
</script>

<template>
  <aside class="files-drawer open">
    <div class="drawer-header">
      <div>
        <span class="eyebrow">{{ mode === 'knowledge' ? 'RAGFlow' : 'Workspace' }}</span>
        <h2>{{ mode === 'knowledge' ? '知识库管理' : '会话文件' }}</h2>
      </div>
      <div class="drawer-actions">
        <button type="button" :aria-label="mode === 'knowledge' ? '刷新知识库' : '刷新文件'" @click="emit('refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v6h-6" /></svg>
        </button>
        <button type="button" aria-label="关闭文件栏" @click="emit('close')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" /></svg>
        </button>
      </div>
    </div>

    <SessionFiles v-if="mode === 'files'" :files="files" @download="emit('download-file', $event)" />
    <KnowledgeBaseManager
      v-else
      :datasets="datasets"
      :documents="documents"
      :selected-dataset="selectedDataset"
      :selected-dataset-id="selectedDatasetId"
      :selected-files="selectedKbFiles"
      :loading="ragflowLoading"
      :uploading="ragflowUploading"
      :message="ragflowMessage"
      :error="ragflowError"
      @select="emit('select-dataset', $event)"
      @file-change="emit('kb-file-change', $event)"
      @remove-file="emit('remove-kb-file', $event)"
      @upload="emit('upload-kb-files')"
      @parse="emit('parse-document', $event)"
      @delete="emit('delete-document', $event)"
    />
  </aside>
</template>
