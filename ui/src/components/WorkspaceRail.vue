<script setup lang="ts">
import type { AgentStatus, ConversationSummary } from '../types'

defineProps<{
  status: AgentStatus
  threadId: string
  fileCount: number
  conversations: ConversationSummary[]
  userName: string
  activeView: 'chat' | 'knowledge'
}>()

const emit = defineEmits<{
  'new-chat': []
  'open-files': []
  'open-knowledge': []
  'select-conversation': [threadId: string]
  'delete-conversation': [conversation: ConversationSummary]
  logout: []
}>()
</script>

<template>
  <aside class="workspace-rail">
    <div class="brand-lockup">
      <div class="brand-mark">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 2.5 15.2 9l6.8 3-6.8 3L12 21.5 8.8 15 2 12l6.8-3L12 2.5Z" />
        </svg>
      </div>
      <div>
        <strong>OmniResearch</strong>
      </div>
    </div>

    <button class="rail-new-chat" type="button" :disabled="status === 'running'" @click="emit('new-chat')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      新对话
    </button>

    <nav class="rail-nav" aria-label="工作区">
      <button type="button" @click="emit('open-files')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h4l2 2h5A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-11Z" /></svg>
        会话文件
        <span>{{ fileCount }}</span>
      </button>
      <button type="button" :class="{ active: activeView === 'knowledge' }" @click="emit('open-knowledge')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2V4Zm2 0v16M10 8h6M10 12h6" /></svg>
        知识库
      </button>
    </nav>

    <section class="conversation-history" aria-label="会话列表">
      <div class="panel-title">会话</div>
      <div v-if="conversations.length === 0" class="empty-state">暂无会话</div>
      <div v-else class="conversation-list">
        <div
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation-item"
          :class="{ active: activeView === 'chat' && conversation.id === threadId }"
        >
          <button
            class="conversation-select"
            type="button"
            :disabled="status === 'running' && conversation.id !== threadId"
            :title="conversation.title"
            @click="emit('select-conversation', conversation.id)"
          >
            <span>{{ conversation.title || '新会话' }}</span>
          </button>
          <button
            class="conversation-delete"
            type="button"
            :disabled="status === 'running'"
            :title="`删除会话：${conversation.title}`"
            :aria-label="`删除会话：${conversation.title}`"
            @click="emit('delete-conversation', conversation)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" />
            </svg>
          </button>
        </div>
      </div>
    </section>

    <div class="rail-account">
      <span>{{ userName.slice(0, 1).toUpperCase() }}</span>
      <strong>{{ userName }}</strong>
      <button type="button" title="退出登录" aria-label="退出登录" @click="emit('logout')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" /></svg>
      </button>
    </div>
  </aside>
</template>
