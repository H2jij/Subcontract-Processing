<!-- components/reconciliation/VarianceIndicator.vue -->
<template>
  <text :class="colorClass">{{ formattedAmount }}</text>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatAmount } from '@/utils/reconciliation/formatters'
import { getVarianceColorClass } from '@/utils/reconciliation/constants'

const props = withDefaults(defineProps<{
  value: number
  showSign?: boolean
}>(), {
  showSign: true,
})

const colorClass = computed(() => {
  const base = getVarianceColorClass(props.value)
  return props.value !== 0 ? `${base} font-semibold` : base
})

const formattedAmount = computed(() => {
  const sign = props.showSign && props.value > 0 ? '+' : ''
  return `${sign}${formatAmount(props.value)}`
})
</script>
