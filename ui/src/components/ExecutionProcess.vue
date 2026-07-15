<script setup lang="ts">
import { ref, watch } from 'vue'

import type { LogItem } from '../types'
import { normalizeTitle } from '../utils/formatters'

const props = defineProps<{
  logs: LogItem[]
  running: boolean
}>()

const detailsRef = ref<HTMLDetailsElement | null>(null)

watch(
  () => props.running,
  (running) => {
    if (detailsRef.value) detailsRef.value.open = running
  },
  { flush: 'post' },
)
</script>

<template>
  <details ref="detailsRef" class="process-card" :open="running">
    <summary>
      <span v-if="running" class="run-pulse"></span>
      执行过程
    </summary>
    <div class="process-list">
      <div v-for="(log, index) in logs" :key="`${log.timestamp}-${index}`" class="process-item" :class="log.type">
        <div class="process-heading">
          <span>{{ normalizeTitle(log.title) }}</span>
          <time>{{ log.timestamp }}</time>
        </div>
        <pre v-if="log.details">{{ JSON.stringify(log.details, null, 2) }}</pre>
      </div>
    </div>
  </details>
</template>
