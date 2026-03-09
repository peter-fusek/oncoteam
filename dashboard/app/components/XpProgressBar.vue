<script setup lang="ts">
const props = defineProps<{
  totalXp: number
  level: string
  streakDays: number
}>()

const { t } = useI18n()

const LEVEL_KEYS = ['intern', 'resident', 'fellow', 'attending', 'chief', 'director', 'distinguished'] as const
const LEVEL_XP = [0, 100, 300, 600, 1000, 2000, 5000]

const levels = computed(() => LEVEL_XP.map((xp, i) => ({
  xp,
  name: t(`components.xp.levels.${LEVEL_KEYS[i]}`),
})))

const levelName = computed(() => {
  const key = props.level.toLowerCase() as typeof LEVEL_KEYS[number]
  return LEVEL_KEYS.includes(key) ? t(`components.xp.levels.${key}`) : props.level
})

const progress = computed(() => {
  let currentIdx = 0
  for (let i = 0; i < levels.value.length; i++) {
    if (props.totalXp >= levels.value[i].xp) currentIdx = i
  }
  const nextLevel = levels.value[currentIdx + 1]
  if (!nextLevel) return { percent: 100, xpToNext: 0, nextName: 'Max' }

  const currentFloor = levels.value[currentIdx].xp
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
      <span class="text-amber-500 font-semibold">{{ levelName }}</span>
      <span class="text-gray-600">{{ totalXp }} XP</span>
    </div>
    <div class="w-24 h-1.5 bg-gray-800 rounded-full overflow-hidden">
      <div
        class="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-500"
        :style="{ width: `${progress.percent}%` }"
      />
    </div>
    <span class="text-gray-600">{{ t('components.xp.toNext', { xp: progress.xpToNext, level: progress.nextName }) }}</span>
    <span v-if="streakDays > 0" class="text-orange-500">{{ t('components.xp.streak', { days: streakDays }) }}</span>
  </div>
</template>
