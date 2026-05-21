<!-- components/reconciliation/SeverityBadge.vue -->
<template>
  <text :class="['text-xs px-2 py-0.5 rounded', badgeClass]">
    {{ label }}
  </text>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getSeverityConfig } from '@/utils/reconciliation/constants'

const props = defineProps<{ severity: 'critical' | 'warning' | 'info' }>()

const config = computed(() => getSeverityConfig(props.severity))
const badgeClass = computed(() => config.value.class)
const label = computed(() => config.value.label)
</script>
