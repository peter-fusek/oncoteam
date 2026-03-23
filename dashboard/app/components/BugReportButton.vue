<script setup lang="ts">
const { activeRole } = useUserRole()
const { locale } = useI18n()
const route = useRoute()

const isOpen = ref(false)
const description = ref('')
const isSubmitting = ref(false)
const submitted = ref(false)
const issueUrl = ref('')
const error = ref('')

const pageText = ref('')

function collectContext() {
  // Grab visible text content (truncated)
  const main = document.querySelector('main')
  pageText.value = (main?.innerText || document.body.innerText || '').slice(0, 2000)
}

async function submit() {
  if (!description.value.trim()) return
  isSubmitting.value = true
  error.value = ''

  try {
    const result = await $fetch<{ created: boolean; number: number; url: string }>('/api/oncoteam/bug-report', {
      method: 'POST',
      body: {
        description: description.value.trim(),
        url: window.location.href,
        route: route.path,
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        role: activeRole.value,
        locale: locale.value,
        page_text: pageText.value,
      },
    })
    if (result.created) {
      submitted.value = true
      issueUrl.value = result.url
    }
  }
  catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to create issue'
  }
  finally {
    isSubmitting.value = false
  }
}

function open() {
  collectContext()
  description.value = ''
  submitted.value = false
  error.value = ''
  issueUrl.value = ''
  isOpen.value = true
}

function close() {
  isOpen.value = false
}
</script>

<template>
  <!-- Floating bug report button — advocate only -->
  <div v-if="activeRole === 'advocate'">
    <button
      class="fixed bottom-6 right-6 z-40 flex h-11 w-11 items-center justify-center rounded-full bg-[var(--clinical-primary)] text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl active:scale-95"
      title="Report a bug"
      @click="open"
    >
      <UIcon name="i-lucide-bug" class="h-5 w-5" />
    </button>

    <!-- Modal overlay -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="close">
          <div class="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl">
            <!-- Success state -->
            <div v-if="submitted" class="text-center">
              <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
                <UIcon name="i-lucide-check" class="h-6 w-6 text-green-600" />
              </div>
              <h3 class="mb-1 text-lg font-semibold text-gray-900">Bug reported</h3>
              <a :href="issueUrl" target="_blank" class="text-sm text-[var(--clinical-primary)] underline">
                View on GitHub
              </a>
              <div class="mt-4">
                <UButton variant="soft" color="neutral" size="sm" @click="close">Close</UButton>
              </div>
            </div>

            <!-- Report form -->
            <div v-else>
              <div class="mb-4 flex items-center gap-2">
                <UIcon name="i-lucide-bug" class="h-5 w-5 text-[var(--clinical-primary)]" />
                <h3 class="text-lg font-semibold text-gray-900">Report a Bug</h3>
              </div>

              <div class="mb-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500">
                <span class="font-medium">{{ route.path }}</span> &middot; {{ activeRole }} &middot; {{ locale }}
              </div>

              <input
                v-model="description"
                type="text"
                placeholder="What's wrong? (one line)"
                class="mb-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-[var(--clinical-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--clinical-primary)]"
                autofocus
                @keydown.enter="submit"
              >

              <p v-if="error" class="mb-2 text-xs text-red-600">{{ error }}</p>

              <div class="flex justify-end gap-2">
                <UButton variant="ghost" color="neutral" size="sm" @click="close">Cancel</UButton>
                <UButton
                  color="primary"
                  size="sm"
                  :loading="isSubmitting"
                  :disabled="!description.trim()"
                  @click="submit"
                >
                  Create Issue
                </UButton>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
