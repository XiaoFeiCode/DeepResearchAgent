<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { marked } from 'marked'

import type { AgentStatus, FileItem, Message } from '../types'
import { formatTime, getFileTag } from '../utils/formatters'
import ExecutionProcess from './ExecutionProcess.vue'

const props = defineProps<{
  messages: Message[]
  status: AgentStatus
  inputQuery: string
  selectedFiles: File[]
  canSend: boolean
  starterPrompts: string[]
}>()

const emit = defineEmits<{
  'update:inputQuery': [value: string]
  send: []
  'file-change': [event: Event]
  'remove-file': [index: number]
  'use-prompt': [prompt: string]
  'download-file': [file: FileItem]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const messagesEndRef = ref<HTMLElement | null>(null)

const renderMarkdown = (text: string) => {
  if (!text) return '<span class="thinking-text">正在分析任务...</span>'
  return marked.parse(text)
}

watch(
  () => props.messages,
  async () => {
    await nextTick()
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
  },
  { deep: true },
)
</script>

<template>
  <section v-if="messages.length === 0" class="welcome-panel">
    <div class="welcome-copy">
      <span class="eyebrow">Ready</span>
      <h2>今天要让哪个助手开工？</h2>
      <p>可以查数据库、检索 RAGFlow、上传资料，也可以把结果整理成文档。</p>
    </div>
    <div class="prompt-grid">
      <button v-for="prompt in starterPrompts" :key="prompt" type="button" @click="emit('use-prompt', prompt)">
        {{ prompt }}
      </button>
    </div>
  </section>

  <section v-else class="chat-scroll-area">
    <div class="chat-list">
      <article v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
        <div v-if="message.role === 'user'" class="message-bubble user-bubble">
          <time>{{ formatTime(message.timestamp) }}</time>
          <p>{{ message.content }}</p>
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
            <div class="message-bubble ai-bubble markdown-body" v-html="renderMarkdown(message.content)"></div>
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
      <div v-for="(file, index) in selectedFiles" :key="`${file.name}-${index}`" class="selected-file">
        <span>{{ getFileTag(file.name) }}</span>
        <strong>{{ file.name }}</strong>
        <button type="button" aria-label="移除文件" @click="emit('remove-file', index)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </div>
    </div>

    <div class="composer">
      <input ref="fileInputRef" type="file" multiple @change="emit('file-change', $event)" />
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
