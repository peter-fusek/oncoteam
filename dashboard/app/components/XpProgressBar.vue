<script setup lang="ts">
const props = defineProps<{
  totalXp: number
  level: string
  streakDays: number
}>()

const LEVELS = [
  { xp: 0, name: 'Intern' },
  { xp: 100, name: 'Resident' },
  { xp: 300, name: 'Fellow' },
  { xp: 600, name: 'Attending' },
  { xp: 1000, name: 'Chief' },
  { xp: 2000, name: 'Director' },
  { xp: 5000, name: 'Distinguished' },
]

const progress = computed(() => {
  let currentIdx = 0
  for (let i = 0; i < LEVELS.length; i++) {
    if (props.totalXp >= LEVELS[i].xp) currentIdx = i
  }
  const nextLevel = LEVELS[currentIdx + 1]
  if (!nextLevel) return { percent: 100, xpToNext: 0, nextName: 'Max' }

  const currentFloor = LEVELS[currentIdx].xp
  const range = nextLevel.xp - currentFloor
  const earned = props.totalXp - currentFloor
  return {
    percent: Math.min(100, Math.round((earned / range) * 100)),
    xpToNext: nextLevel.xp - props.totalXp,
    nextName: nextLevel.name,
  }
})
</script>

<template>
  <div class="flex items-center gap-3 text-xs">
    <div class="flex items-center gap-1.5">
      <span class="text-amber-500 font-semibold">{{ level }}</span>
      <span class="text-gray-600">{{ totalXp }} XP</span>
    </div>
    <div class="w-24 h-1.5 bg-gray-800 rounded-full overflow-hidden">
      <div
        class="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500"
        :style="{ width: `${progress.percent}%` }"
      />
    </div>
    <span class="text-gray-600">{{ progress.xpToNext }} to {{ progress.nextName }}</span>
    <span v-if="streakDays > 0" class="text-orange-500">{{ streakDays }}d streak</span>
  </div>
</template>
