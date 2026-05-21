<!-- components/reconciliation/ListContainer.vue -->
<template>
  <scroll-view
    scroll-y
    class="h-full"
    :refresher-enabled="true"
    :refresher-triggered="refreshing"
    @refresherrefresh="handleRefresh"
    @scrolltolower="handleLoadMore"
  >
    <SkeletonLoader v-if="loading && !list.length" :count="3" />
    <slot v-else-if="list.length" />
    <EmptyState v-else :message="emptyText" />
    <view v-if="loadingMore" class="py-4 text-center text-gray-400 text-sm">
      加载中...
    </view>
    <view v-if="!hasMore && list.length" class="py-4 text-center text-gray-400 text-sm">
      没有更多了
    </view>
  </scroll-view>
</template>

<script setup lang="ts">
import SkeletonLoader from './SkeletonLoader.vue'
import EmptyState from './EmptyState.vue'

withDefaults(defineProps<{
  list: any[]
  loading: boolean
  loadingMore: boolean
  refreshing: boolean
  hasMore: boolean
  emptyText?: string
}>(), {
  emptyText: '暂无数据',
})

const emit = defineEmits<{
  refresh: []
  loadMore: []
}>()

const handleRefresh = () => emit('refresh')
const handleLoadMore = () => emit('loadMore')
</script>
