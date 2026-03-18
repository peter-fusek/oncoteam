import { useDb } from '../utils/db'
import { gamificationStats } from '../db/schema'

const LEVELS = [
  { xp: 0, name: 'Intern' },
  { xp: 100, name: 'Resident' },
  { xp: 300, name: 'Fellow' },
  { xp: 600, name: 'Attending' },
  { xp: 1000, name: 'Chief' },
  { xp: 2000, name: 'Director' },
  { xp: 5000, name: 'Distinguished' },
]

function getNextLevel(xp: number) {
  for (const l of LEVELS) {
    if (xp < l.xp) return { name: l.name, xpRequired: l.xp }
  }
  return { name: 'Max', xpRequired: xp }
}

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  if (!session.user) throw createError({ statusCode: 401, message: 'Not authenticated' })
  const config = useRuntimeConfig()

  if (!config.databaseUrl) {
    return { totalXp: 0, level: 'Intern', streakDays: 0, lastActive: null, nextLevel: 'Resident', xpToNext: 100 }
  }

  const db = useDb()
  const stats = await db.select().from(gamificationStats).limit(1)

  if (!stats.length) {
    return { totalXp: 0, level: 'Intern', streakDays: 0, lastActive: null, nextLevel: 'Resident', xpToNext: 100 }
  }

  const s = stats[0]
  const next = getNextLevel(s.totalXp)

  return {
    totalXp: s.totalXp,
    level: s.level,
    streakDays: s.streakDays,
    lastActive: s.lastActive,
    nextLevel: next.name,
    xpToNext: next.xpRequired - s.totalXp,
  }
})
