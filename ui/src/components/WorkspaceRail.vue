<script setup lang="ts">
import type { AgentStatus, LogItem } from '../types'
import { normalizeTitle } from '../utils/formatters'

defineProps<{
  status: AgentStatus
  threadId: string
  fileCount: number
  logs: LogItem[]
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
        <strong>{{ threadId.slice(0, 8) }}</strong>
      </div>
      <div class="status-row">
        <span>文件</span>
        <strong>{{ fileCount }}</strong>
      </div>
    </div>

    <div class="activity-panel">
      <div class="panel-title">最近动作</div>
      <div v-if="logs.length === 0" class="empty-state">等待任务开始</div>
      <div v-else class="activity-list">
        <div v-for="(log, index) in logs" :key="`${log.timestamp}-${index}`" class="activity-item">
          <span class="activity-dot" :class="log.type"></span>
          <div>
            <strong>{{ normalizeTitle(log.title) }}</strong>
            <time>{{ log.timestamp }}</time>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>
