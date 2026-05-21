<!-- components/reconciliation/ConfirmDialog.vue -->
<template>
  <uni-popup ref="popup" type="dialog">
    <uni-popup-dialog
      :type="type"
      :title="title"
      :content="content"
      :before-close="true"
      @confirm="handleConfirm"
      @close="handleClose"
    />
  </uni-popup>
</template>

<script setup lang="ts">
import { ref } from 'vue'

withDefaults(defineProps<{
  title?: string
  content: string
  type?: 'info' | 'warning' | 'error'
}>(), {
  title: '提示',
  type: 'info',
})

const popup = ref()
const emit = defineEmits<{ confirm: []; close: [] }>()

const open = () => popup.value?.open()
const handleConfirm = () => { emit('confirm'); popup.value?.close() }
const handleClose = () => { emit('close'); popup.value?.close() }

defineExpose({ open })
</script>
