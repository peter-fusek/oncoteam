<script setup lang="ts">
const props = defineProps<{ error: { statusCode: number; message: string; statusMessage?: string } }>()

function handleRetry() {
  clearError({ redirect: '/' })
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen bg-gray-50">
    <div class="text-center space-y-4 p-8">
      <div class="text-6xl font-bold text-gray-200">{{ error.statusCode || 500 }}</div>
      <h1 class="text-xl font-semibold text-gray-900">
        {{ error.statusMessage || 'Something went wrong' }}
      </h1>
      <p class="text-sm text-gray-500 max-w-md">
        {{ error.message }}
      </p>
      <button
        class="mt-4 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 transition-colors"
        @click="handleRetry"
      >
        Back to Home
      </button>
    </div>
  </div>
</template>
