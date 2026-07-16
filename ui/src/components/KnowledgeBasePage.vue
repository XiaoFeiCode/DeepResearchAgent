<script setup lang="ts">
import type { RagflowDataset, RagflowDocument } from '../types'
import KnowledgeBaseManager from './KnowledgeBaseManager.vue'

defineProps<{
  datasets: RagflowDataset[]
  documents: RagflowDocument[]
  selectedDataset?: RagflowDataset
  selectedDatasetId: string
  selectedFiles: File[]
  loading: boolean
  uploading: boolean
  creating: boolean
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
</script>

<template>
  <section class="knowledge-page">
    <header class="knowledge-page-header">
      <div>
        <span class="eyebrow">RAGFlow</span>
        <h1>知识库管理</h1>
        <p>创建知识库、上传文档、查看解析状态并维护可供 Agent 检索的资料。</p>
      </div>
      <div class="knowledge-page-actions">
        <button type="button" class="secondary-button" @click="emit('refresh')">刷新</button>
        <button type="button" class="primary-button" @click="emit('back')">返回对话</button>
      </div>
    </header>

    <form class="dataset-create-form" @submit.prevent="emit('create')">
      <div class="dataset-create-copy">
        <strong>新建知识库</strong>
        <span>创建后可立即上传 PDF、DOCX、TXT 等资料。</span>
      </div>
      <input
        :value="newDatasetName"
        maxlength="128"
        placeholder="知识库名称"
        @input="emit('update:newDatasetName', ($event.target as HTMLInputElement).value)"
      />
      <input
        :value="newDatasetDescription"
        maxlength="1000"
        placeholder="说明（可选）"
        @input="emit('update:newDatasetDescription', ($event.target as HTMLInputElement).value)"
      />
      <button class="primary-button" type="submit" :disabled="creating">
        {{ creating ? '创建中...' : '创建' }}
      </button>
    </form>

    <div class="knowledge-page-content">
      <KnowledgeBaseManager
        :datasets="datasets"
        :documents="documents"
        :selected-dataset="selectedDataset"
        :selected-dataset-id="selectedDatasetId"
        :selected-files="selectedFiles"
        :loading="loading"
        :uploading="uploading"
        :message="message"
        :error="error"
        @select="emit('select', $event)"
        @file-change="emit('file-change', $event)"
        @remove-file="emit('remove-file', $event)"
        @upload="emit('upload')"
        @parse="emit('parse', $event)"
        @delete="emit('delete', $event)"
      />
    </div>
  </section>
</template>