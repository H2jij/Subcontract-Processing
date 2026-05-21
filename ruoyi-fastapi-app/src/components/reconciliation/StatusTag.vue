<!-- components/reconciliation/StatusTag.vue -->
<template>
  <text :class="['text-xs px-2 py-0.5 rounded-full', tagClass]">
    {{ label }}
  </text>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getStatusConfig } from '@/utils/reconciliation/constants'

const props = defineProps<{
  status: string
  type?: 'statement' | 'settlement' | 'payment' | 'anomaly'
}>()

const config = computed(() => getStatusConfig(props.status, props.type))
const tagClass = computed(() => config.value.class)
const label = computed(() => config.value.label)
</script>
