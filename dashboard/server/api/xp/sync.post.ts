import { eq, sql } from 'drizzle-orm'
import { useDb } from '../../utils/db'
import { gamificationStats, xpEvents, xpLog } from '../../db/schema'

// XP rules per tool/activity type
const XP_RULES: Record<string, number> = {
  search_pubmed: 10,
  search_clinical_trials: 10,
  search_clinical_trials_adjacent: 10,
  fetch_pubmed_article: 5,
  fetch_trial_details: 5,
  check_trial_eligibility: 15,
  daily_briefing: 25,
  analyze_labs: 10,
  compare_labs: 10,
  get_lab_trends: 5,
  search_documents: 5,
  view_document: 5,
  get_patient_context: 3,
  log_research_decision: 10,
  summarize_session: 15,
  review_session: 10,
  create_improvement_issue: 20,
  // Autonomous tasks
  pre_cycle_check: 30,
  tumor_marker_review: 20,
  response_assessment: 25,
  daily_research: 50,
  trial_monitor: 30,
  file_scan: 10,
  weekly_briefing: 50,
  mtb_preparation: 40,
}

// Level thresholds
const LEVELS = [
  { xp: 0, name: 'Intern' },
  { xp: 100, name: 'Resident' },
  { xp: 300, name: 'Fellow' },
  { xp: 600, name: 'Attending' },
  { xp: 1000, name: 'Chief' },
  { xp: 2000, name: 'Director' },
  { xp: 5000, name: 'Distinguished' },
]

function getLevel(xp: number): string {
  let level = LEVELS[0].name
  for (const l of LEVELS) {
    if (xp >= l.xp) level = l.name
  }
  return level
}

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()

  if (!config.databaseUrl) {
    return { error: 'Database not configured', synced: 0 }
  }

  const db = useDb()
  const apiUrl = config.public.oncoteamApiUrl

  // Fetch recent activity from oncoteam backend
  const response = await $fetch<{ entries: Array<{ tool: string; timestamp: string }> }>(
    `${apiUrl}/api/activity?limit=50`
  ).catch(() => ({ entries: [] }))

  if (!response.entries?.length) {
    return { synced: 0, message: 'No new activity' }
  }

  // Get last sync timestamp
  const existing = await db.select().from(xpEvents).orderBy(sql`created_at DESC`).limit(1)
  const lastSync = existing[0]?.createdAt ?? new Date(0)

  // Filter new activities and compute XP
  let synced = 0
  let totalNewXp = 0

  for (const entry of response.entries) {
    const entryDate = new Date(entry.timestamp)
    if (entryDate <= lastSync) continue

    const xp = XP_RULES[entry.tool] ?? 5
    totalNewXp += xp

    await db.insert(xpEvents).values({
      agentId: 'oncoteam',
      xpAmount: xp,
      sourceTool: entry.tool,
      createdAt: entryDate,
    })

    await db.insert(xpLog).values({
      toolName: entry.tool,
      xpEarned: xp,
    })

    synced++
  }

  // Update gamification stats
  if (totalNewXp > 0) {
    const stats = await db.select().from(gamificationStats).limit(1)
    const currentXp = (stats[0]?.totalXp ?? 0) + totalNewXp
    const level = getLevel(currentXp)
    const today = new Date().toISOString().slice(0, 10)

    if (stats.length === 0) {
      await db.insert(gamificationStats).values({
        totalXp: currentXp,
        level,
        lastActive: new Date(),
        streakDays: 1,
        streakLastDate: today,
      })
    } else {
      const streakDays = stats[0].streakLastDate === today
        ? stats[0].streakDays
        : stats[0].streakDays + 1

      await db.update(gamificationStats)
        .set({
          totalXp: currentXp,
          level,
          lastActive: new Date(),
          streakDays,
          streakLastDate: today,
        })
        .where(eq(gamificationStats.id, stats[0].id))
    }
  }

  return { synced, totalNewXp, message: `Synced ${synced} activities (+${totalNewXp} XP)` }
})
