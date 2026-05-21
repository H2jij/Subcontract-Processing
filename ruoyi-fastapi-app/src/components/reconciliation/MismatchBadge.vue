<!-- components/reconciliation/MismatchBadge.vue -->
<template>
  <view v-if="show" class="flex items-center">
    <view class="w-1 h-full bg-red-500 rounded-full mr-2" />
    <text class="text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded">
      货不对板
    </text>
  </view>
</template>

<script setup lang="ts">
defineProps<{ show: boolean }>()
</script>
