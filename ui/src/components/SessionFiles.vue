<script setup lang="ts">
import type { FileItem } from '../types'
import { formatBytes, getFileTag } from '../utils/formatters'

defineProps<{ files: FileItem[] }>()

const emit = defineEmits<{
  download: [file: FileItem]
}>()
</script>

<template>
  <div class="drawer-section">
    <div v-if="!files.length" class="drawer-empty">
      <div class="mini-illustration"></div>
      <p>还没有生成文件</p>
    </div>
    <div v-else class="drawer-files">
      <button v-for="file in files" :key="file.path" type="button" class="drawer-file" @click="emit('download', file)">
        <span class="file-tag">{{ getFileTag(file.name) }}</span>
        <div>
          <strong>{{ file.name }}</strong>
          <small>{{ formatBytes(file.size) }}</small>
        </div>
      </button>
    </div>
  </div>
</template>
