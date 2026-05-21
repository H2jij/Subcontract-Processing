<!-- components/reconciliation/FilterPanel.vue -->
<template>
  <uni-popup ref="popup" type="top">
    <view class="bg-white p-4 rounded-b-xl shadow-lg">
      <slot />
      <view class="flex gap-3 mt-4">
        <button class="flex-1 btn-secondary" @click="handleReset">重置</button>
        <button class="flex-1 btn-primary" @click="handleConfirm">确认</button>
      </view>
    </view>
  </uni-popup>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const popup = ref()
const emit = defineEmits<{
  confirm: []
  reset: []
}>()

const open = () => popup.value?.open()
const close = () => popup.value?.close()
const handleReset = () => { emit('reset'); close() }
const handleConfirm = () => { emit('confirm'); close() }

defineExpose({ open, close })
</script>
