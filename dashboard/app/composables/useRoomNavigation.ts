export interface RoomDef {
  key: string
  name: string
  desc: string
  icon: string
  color: string
  border: string
  statusColor: string
  tools: string[]
  autonomousJobs: string[]
  status: 'active' | 'recent' | 'idle'
  totalCalls: number
}

export function useRoomNavigation() {
  const currentLevel = ref<0 | 1 | 2>(0)
  const selectedRoom = ref<RoomDef | null>(null)
  const selectedWorker = ref<string | null>(null)

  // Track last-viewed timestamp for "new activity" badges
  const lastViewed = ref<string>(new Date(0).toISOString())

  if (import.meta.client) {
    const stored = localStorage.getItem('oncoteam_agents_last_viewed')
    if (stored) lastViewed.value = stored
  }

  function markViewed() {
    const now = new Date().toISOString()
    lastViewed.value = now
    if (import.meta.client) {
      localStorage.setItem('oncoteam_agents_last_viewed', now)
    }
  }

  function openRoom(room: RoomDef) {
    selectedRoom.value = room
    selectedWorker.value = null
    currentLevel.value = 1
  }

  function openWorker(toolName: string) {
    selectedWorker.value = toolName
    currentLevel.value = 2
  }

  function goBack() {
    if (currentLevel.value === 2) {
      selectedWorker.value = null
      currentLevel.value = 1
    } else if (currentLevel.value === 1) {
      selectedRoom.value = null
      currentLevel.value = 0
    }
  }

  function goToGrid() {
    selectedRoom.value = null
    selectedWorker.value = null
    currentLevel.value = 0
  }

  return {
    currentLevel,
    selectedRoom,
    selectedWorker,
    lastViewed,
    markViewed,
    openRoom,
    openWorker,
    goBack,
    goToGrid,
  }
}
