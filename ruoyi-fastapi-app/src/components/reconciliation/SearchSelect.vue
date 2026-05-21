<!-- components/reconciliation/SearchSelect.vue -->
<template>
  <view class="relative">
    <view class="flex items-center border border-gray-300 rounded-lg px-3 py-2 bg-white">
      <text class="text-gray-400 mr-2 text-sm">🔍</text>
      <input
        class="flex-1 text-sm"
        :placeholder="placeholder"
        :value="searchText"
        @input="handleInput"
        @focus="showDropdown = true"
      />
      <text
        v-if="modelValue != null"
        class="text-gray-400 text-sm ml-2"
        @click="handleClear"
      >✕</text>
    </view>
    <view
      v-if="showDropdown && $slots.default"
      class="absolute left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 max-h-48 overflow-y-auto"
    >
      <slot />
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  placeholder?: string
  modelValue: number | null
}>(), {
  placeholder: '请输入搜索关键词',
})

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  search: [keyword: string]
}>()

const searchText = ref('')
const showDropdown = ref(false)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

const handleInput = (e: any) => {
  const value = e.detail?.value ?? e.target?.value ?? ''
  searchText.value = value

  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('search', value)
  }, 300)
}

const handleClear = () => {
  searchText.value = ''
  showDropdown.value = false
  emit('update:modelValue', null)
}

watch(() => props.modelValue, (val) => {
  if (val == null) {
    searchText.value = ''
  }
})
</script>
