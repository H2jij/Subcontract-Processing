<!-- components/reconciliation/SkeletonLoader.vue -->
<template>
  <view class="px-4">
    <view
      v-for="i in count"
      :key="i"
      class="mb-3 p-4 bg-white rounded-lg shadow-sm animate-pulse"
    >
      <view class="h-4 bg-gray-200 rounded w-3/4 mb-3" />
      <view class="h-3 bg-gray-200 rounded w-1/2 mb-2" />
      <view class="h-3 bg-gray-200 rounded w-2/3" />
    </view>
  </view>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  count?: number
}>(), {
  count: 3,
})
</script>
