<script setup lang="ts">
import { ref } from 'vue'

import type { RagflowDataset, RagflowDocument } from '../types'
import { getFileTag } from '../utils/formatters'

defineProps<{
  datasets: RagflowDataset[]
  documents: RagflowDocument[]
  selectedDataset?: RagflowDataset
  selectedDatasetId: string
  selectedFiles: File[]
  loading: boolean
  uploading: boolean
  message: string
  error: string
}>()

const emit = defineEmits<{
  select: [dataset: RagflowDataset]
  'file-change': [event: Event]
  'remove-file': [index: number]
  upload: []
  parse: [document: RagflowDocument]
  delete: [document: RagflowDocument]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
</script>

<template>
  <div class="knowledge-manager">
    <div v-if="error" class="inline-alert error">{{ error }}</div>
    <div v-if="message" class="inline-alert success">{{ message }}</div>

    <div v-if="loading && !datasets.length" class="drawer-empty compact"><p>正在读取 RAGFlow 知识库...</p></div>
    <div v-else-if="!datasets.length" class="drawer-empty compact">
      <div class="mini-illustration"></div>
      <p>当前没有知识库</p>
    </div>

    <template v-else>
      <div class="dataset-list">
        <button
          v-for="dataset in datasets"
          :key="dataset.id"
          type="button"
          class="dataset-card"
          :class="{ active: selectedDatasetId === dataset.id }"
          @click="emit('select', dataset)"
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
        <input ref="fileInputRef" type="file" multiple @change="emit('file-change', $event)" />
        <button class="kb-pick-button" type="button" :disabled="uploading" @click="fileInputRef?.click()">选择文件</button>
        <div v-if="selectedFiles.length" class="kb-selected-files">
          <div v-for="(file, index) in selectedFiles" :key="`${file.name}-${index}`" class="kb-selected-file">
            <span>{{ getFileTag(file.name) }}</span>
            <strong>{{ file.name }}</strong>
            <button type="button" aria-label="移除知识库上传文件" @click="emit('remove-file', index)">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" /></svg>
            </button>
          </div>
        </div>
        <button
          class="kb-upload-button"
          type="button"
          :disabled="!selectedDatasetId || !selectedFiles.length || uploading"
          @click="emit('upload')"
        >
          {{ uploading ? '上传中...' : '上传并解析' }}
        </button>
      </section>

      <section class="document-panel">
        <div class="document-panel-title"><strong>文档列表</strong><small>{{ documents.length }} 个</small></div>
        <div v-if="!documents.length" class="drawer-empty compact"><p>这个知识库还没有文档</p></div>
        <div v-else class="document-list">
          <article v-for="document in documents" :key="document.id" class="document-card">
            <div class="document-main">
              <span class="file-tag">{{ getFileTag(document.name) }}</span>
              <div>
                <strong>{{ document.name }}</strong>
                <small>
                  状态: {{ document.run ?? '未知' }}
                  <template v-if="document.chunk_count !== null && document.chunk_count !== undefined"> · {{ document.chunk_count }} 切片</template>
                </small>
              </div>
            </div>
            <div class="document-actions">
              <button type="button" @click="emit('parse', document)">解析</button>
              <button type="button" class="danger" @click="emit('delete', document)">删除</button>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>
