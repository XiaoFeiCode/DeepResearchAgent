<script setup lang="ts">
import { ref } from 'vue'

import type { ImageKnowledgeItem } from '../types'

defineProps<{
  images: ImageKnowledgeItem[]
  selectedFiles: File[]
  description: string
  loading: boolean
  uploading: boolean
  message: string
  error: string
}>()

const emit = defineEmits<{
  'update:description': [value: string]
  'file-change': [event: Event]
  'remove-file': [index: number]
  upload: []
  delete: [image: ImageKnowledgeItem]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
</script>

<template>
  <div class="image-knowledge-manager">
    <div v-if="error" class="inline-alert error">{{ error }}</div>
    <div v-if="message" class="inline-alert success">{{ message }}</div>

    <section class="image-index-panel">
      <div>
        <strong>添加图片到检索库</strong>
        <small>上传后自动生成跨模态向量，可用于文搜图和图搜图</small>
      </div>
      <input
        ref="fileInputRef"
        type="file"
        multiple
        accept=".png,.jpg,.jpeg,.webp"
        @change="emit('file-change', $event)"
      />
      <button type="button" :disabled="uploading" @click="fileInputRef?.click()">选择图片</button>
      <textarea
        :value="description"
        rows="2"
        placeholder="可选：填写图片来源或业务说明"
        @input="emit('update:description', ($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <div v-if="selectedFiles.length" class="kb-selected-files">
        <div v-for="(file, index) in selectedFiles" :key="`${file.name}-${index}`" class="kb-selected-file">
          <span>IMG</span>
          <strong>{{ file.name }}</strong>
          <button type="button" aria-label="移除图片" @click="emit('remove-file', index)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" /></svg>
          </button>
        </div>
      </div>
      <button
        class="kb-upload-button"
        type="button"
        :disabled="!selectedFiles.length || uploading"
        @click="emit('upload')"
      >
        {{ uploading ? '正在向量化...' : '上传并建立索引' }}
      </button>
    </section>

    <div v-if="loading && !images.length" class="drawer-empty compact"><p>正在读取图片库...</p></div>
    <div v-else-if="!images.length" class="drawer-empty compact">
      <div class="mini-illustration image-illustration"></div>
      <p>图片库中还没有图片</p>
    </div>
    <section v-else class="image-library-grid">
      <article v-for="image in images" :key="image.id" class="image-library-item">
        <a v-if="image.previewUrl" :href="image.previewUrl" target="_blank" rel="noreferrer">
          <img :src="image.previewUrl" :alt="image.filename" />
        </a>
        <div v-else class="image-loading">IMG</div>
        <div class="image-library-meta">
          <strong>{{ image.filename }}</strong>
          <small>{{ image.description || '暂无说明' }}</small>
        </div>
        <button class="danger" type="button" @click="emit('delete', image)">删除</button>
      </article>
    </section>
  </div>
</template>
