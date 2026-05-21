<!-- components/reconciliation/EmptyState.vue -->
<template>
  <view class="flex flex-col items-center justify-center py-16">
    <text v-if="icon" class="text-4xl mb-4">{{ icon }}</text>
    <view v-else class="w-16 h-16 mb-4 rounded-full bg-gray-100 flex items-center justify-center">
      <text class="text-2xl text-gray-300">📋</text>
    </view>
    <text class="text-sm text-gray-400">{{ message }}</text>
  </view>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  message?: string
  icon?: string
}>(), {
  message: '暂无数据',
})
</script>
