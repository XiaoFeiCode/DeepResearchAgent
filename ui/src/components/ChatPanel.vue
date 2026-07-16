<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { marked } from 'marked'

import type { AgentStatus, FileItem, RagflowImage, Message } from '../types'
import { formatTime, getFileTag } from '../utils/formatters'
import ExecutionProcess from './ExecutionProcess.vue'

marked.setOptions({
  gfm: true,
  breaks: false,
})

const props = defineProps<{
  messages: Message[]
  status: AgentStatus
  inputQuery: string
  selectedFiles: File[]
  canSend: boolean
}>()

const emit = defineEmits<{
  'update:inputQuery': [value: string]
  send: []
  'file-change': [event: Event]
  'remove-file': [index: number]
  'download-file': [file: FileItem]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const messagesEndRef = ref<HTMLElement | null>(null)
const imagePreviewUrls = new Map<File, string>()

const isPreviewableImage = (file: File) => {
  const suffix = file.name.split('.').pop()?.toLowerCase()
  return ['png', 'jpg', 'jpeg', 'webp'].includes(suffix || '')
}

const getImagePreviewUrl = (file: File) => {
  const existing = imagePreviewUrls.get(file)
  if (existing) return existing

  const previewUrl = URL.createObjectURL(file)
  imagePreviewUrls.set(file, previewUrl)
  return previewUrl
}

const renderMarkdown = (text: string) => {
  if (!text) return '<span class="thinking-text">正在分析任务...</span>'
  return marked.parse(text)
}

const escapeHtml = (value: string) => value
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#039;')

const imageFigureHtml = (image: RagflowImage) => {
  const title = image.document_name || image.filename || '检索图片'
  const source = image.source === 'ragflow'
    ? `RAGFlow 文档图片${image.page ? ` · 第 ${image.page} 页` : ''}`
    : image.score !== undefined
      ? `相似度 ${(image.score * 100).toFixed(1)}%`
      : '图片知识库'
  const media = image.previewUrl
    ? `<a href="${escapeHtml(image.previewUrl)}" target="_blank" rel="noreferrer"><img src="${escapeHtml(image.previewUrl)}" alt="${escapeHtml(title)}" loading="lazy"></a>`
    : '<div class="inline-image-loading">图片加载中...</div>'
  const description = image.description
    ? `<small>${escapeHtml(image.description)}</small>`
    : ''

  return `<figure class="inline-image-result" data-image-id="${escapeHtml(image.id)}">
    ${media}
    <figcaption>
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(source)}</span>
      ${description}
    </figcaption>
  </figure>`
}

const renderMessageContent = (message: Message) => {
  if (!message.content) return '<span class="thinking-text">正在分析任务...</span>'
  const images = message.images ?? []
  if (!images.length) return renderMarkdown(message.content)

  const referencedIds = new Set<string>()
  const imageSlots: Array<{ marker: string; image: RagflowImage }> = []
  const source = message.content.replace(
    /\{\{\s*image:([^}\s]+)\s*\}\}/gi,
    (token, imageId: string) => {
      const image = images.find((item) => item.id === imageId)
      if (!image) return token
      referencedIds.add(image.id)
      const marker = `INLINE_IMAGE_SLOT_${imageSlots.length}_${image.id}`
      imageSlots.push({ marker, image })
      return `\n\n${marker}\n\n`
    },
  )
  let html = marked.parse(source) as string
  for (const slot of imageSlots) {
    const figure = imageFigureHtml(slot.image)
    html = html.replace(`<p>${slot.marker}</p>`, figure)
    html = html.replace(slot.marker, figure)
  }
  const remaining = images.filter((image) => !referencedIds.has(image.id))
  if (!remaining.length) return html

  // 模型漏写图片占位符时，把图片均匀插入正文块之间，避免全部堆在答案末尾。
  const document = new DOMParser().parseFromString(
    `<div id="message-content-root">${html}</div>`,
    'text/html',
  )
  const root = document.querySelector('#message-content-root')
  if (!root) return html
  const anchors = Array.from(root.children).filter((element) => (
    !element.classList.contains('inline-image-result')
    && ['P', 'H1', 'H2', 'H3', 'UL', 'OL', 'TABLE', 'BLOCKQUOTE'].includes(element.tagName)
  ))

  if (!anchors.length) {
    root.insertAdjacentHTML('beforeend', remaining.map(imageFigureHtml).join(''))
    return root.innerHTML
  }

  // 倒序插入可以保证多张图片落在同一锚点后时仍保持检索顺序。
  for (let index = remaining.length - 1; index >= 0; index -= 1) {
    const image = remaining[index]
    if (!image) continue
    const anchorIndex = Math.min(
      anchors.length - 1,
      Math.max(0, Math.floor(((index + 1) * anchors.length) / (remaining.length + 1))),
    )
    anchors[anchorIndex]?.insertAdjacentHTML('afterend', imageFigureHtml(image))
  }
  return root.innerHTML
}

watch(
  () => props.messages,
  async () => {
    await nextTick()
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
  },
  { deep: true },
)

watch(
  () => props.selectedFiles,
  (files) => {
    for (const [file, previewUrl] of imagePreviewUrls) {
      if (!files.includes(file)) {
        URL.revokeObjectURL(previewUrl)
        imagePreviewUrls.delete(file)
      }
    }
  },
)

onBeforeUnmount(() => {
  for (const previewUrl of imagePreviewUrls.values()) URL.revokeObjectURL(previewUrl)
  imagePreviewUrls.clear()
})
</script>

<template>
  <section v-if="messages.length === 0" class="welcome-panel">
    <div class="welcome-copy empty-chat-state">
      <div class="empty-chat-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M12 3 14.9 9.1 21 12l-6.1 2.9L12 21l-2.9-6.1L3 12l6.1-2.9L12 3Z" /></svg>
      </div>
      <h2>有什么可以帮忙的？</h2>
    </div>
  </section>

  <section v-else class="chat-scroll-area">
    <div class="chat-list">
      <article v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
        <div v-if="message.role === 'user'" class="user-message-content">
          <div v-if="message.attachments?.length" class="user-message-attachments">
            <a
              v-for="attachment in message.attachments.filter((item) => item.content_type.startsWith('image/'))"
              :key="attachment.content_url"
              :href="attachment.previewUrl"
              class="user-image-attachment"
              :class="{ loading: !attachment.previewUrl }"
              target="_blank"
              rel="noreferrer"
              :aria-label="`查看图片：${attachment.name}`"
            >
              <img v-if="attachment.previewUrl" :src="attachment.previewUrl" :alt="attachment.name" />
              <span v-else>图片加载中...</span>
            </a>
            <div
              v-for="attachment in message.attachments.filter((item) => !item.content_type.startsWith('image/'))"
              :key="attachment.content_url"
              class="user-file-attachment"
            >
              <span>{{ getFileTag(attachment.name) }}</span>
              <strong>{{ attachment.name }}</strong>
            </div>
          </div>
          <div class="message-bubble user-bubble">
            <time>{{ formatTime(message.timestamp) }}</time>
            <p>{{ message.content }}</p>
          </div>
        </div>

        <div v-else-if="message.role === 'ai'" class="assistant-message">
          <div class="assistant-avatar">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3 14.9 9.1 21 12l-6.1 2.9L12 21l-2.9-6.1L3 12l6.1-2.9L12 3Z" />
            </svg>
          </div>
          <div class="assistant-body">
            <ExecutionProcess
              v-if="message.logs?.length"
              :logs="message.logs"
              :running="status === 'running' && index === messages.length - 1"
            />
            <div class="message-bubble ai-bubble markdown-body" v-html="renderMessageContent(message)"></div>
            <div v-if="message.files?.length" class="result-files">
              <button v-for="file in message.files" :key="file.name" type="button" @click="emit('download-file', file)">
                <span>{{ getFileTag(file.name) }}</span>
                <strong>{{ file.name }}</strong>
              </button>
            </div>
          </div>
        </div>

        <div v-else class="system-message">{{ message.content }}</div>
      </article>
      <div ref="messagesEndRef" class="scroll-anchor"></div>
    </div>
  </section>

  <footer class="composer-area">
    <div v-if="selectedFiles.length" class="selected-files">
      <div
        v-for="(file, index) in selectedFiles"
        :key="`${file.name}-${index}`"
        class="selected-file"
        :class="{ 'image-file': isPreviewableImage(file) }"
      >
        <img
          v-if="isPreviewableImage(file)"
          :src="getImagePreviewUrl(file)"
          :alt="file.name"
        />
        <span v-else>{{ getFileTag(file.name) }}</span>
        <strong>{{ file.name }}</strong>
        <button type="button" aria-label="移除文件" @click="emit('remove-file', index)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </div>
    </div>

    <div class="composer">
      <input
        ref="fileInputRef"
        type="file"
        multiple
        accept=".md,.txt,.docx,.pdf,.xlsx,.xls,.png,.jpg,.jpeg,.webp"
        @change="emit('file-change', $event)"
      />
      <button class="icon-button" type="button" :disabled="status === 'running'" aria-label="上传文件" @click="fileInputRef?.click()">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v10m0-10 4 4m-4-4-4 4M5 19h14" /></svg>
      </button>
      <textarea
        :value="inputQuery"
        :disabled="status === 'running'"
        placeholder="输入任务..."
        rows="1"
        @input="emit('update:inputQuery', ($event.target as HTMLTextAreaElement).value)"
        @keydown.enter.exact.prevent="emit('send')"
      ></textarea>
      <button class="send-button" type="button" :disabled="!canSend" aria-label="发送" @click="emit('send')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 12 15-7-4 14-3-6-8-1Z" /></svg>
      </button>
    </div>
  </footer>
</template>
