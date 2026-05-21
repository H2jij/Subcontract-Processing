<!-- components/reconciliation/AmountDisplay.vue -->
<template>
  <text :class="['font-mono', sizeClass]">{{ formatted }}</text>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatAmount } from '@/utils/reconciliation/formatters'

const props = withDefaults(defineProps<{
  value: number
  size?: 'sm' | 'md' | 'lg'
}>(), {
  size: 'md',
})

const formatted = computed(() => formatAmount(props.value))

const sizeClass = computed(() => {
  switch (props.size) {
    case 'lg': return 'text-xl font-bold'
    case 'sm': return 'text-xs'
    default: return 'text-sm font-medium'
  }
})
</script>
