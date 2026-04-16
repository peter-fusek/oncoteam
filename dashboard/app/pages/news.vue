<script setup lang="ts">
// News merged into Research page (#350) — redirect for backward compat
await navigateTo('/research?tab=news', { redirectCode: 301 })
</script>

<template>
  <div />
</template>
