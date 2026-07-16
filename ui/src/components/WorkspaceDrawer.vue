<script setup lang="ts">
import type { FileItem } from '../types'
import SessionFiles from './SessionFiles.vue'

defineProps<{
  files: FileItem[]
}>()

const emit = defineEmits<{
  close: []
  refresh: []
  'download-file': [file: FileItem]
}>()
</script>

<template>
  <aside class="files-drawer open">
    <div class="drawer-header">
      <div>
        <span class="eyebrow">Workspace</span>
        <h2>会话文件</h2>
      </div>
      <div class="drawer-actions">
        <button type="button" aria-label="刷新文件" @click="emit('refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v6h-6" /></svg>
        </button>
        <button type="button" aria-label="关闭文件栏" @click="emit('close')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" /></svg>
        </button>
      </div>
    </div>
    <SessionFiles :files="files" @download="emit('download-file', $event)" />
  </aside>
</template>