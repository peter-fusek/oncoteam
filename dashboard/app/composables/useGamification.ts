interface XpConfig {
  [tool: string]: number
}

const XP_TABLE: XpConfig = {
  search_pubmed: 10,
  search_clinical_trials: 15,
  search_clinical_trials_adjacent: 15,
  daily_briefing: 50,
  check_trial_eligibility: 25,
  fetch_pubmed_article: 5,
  fetch_trial_details: 5,
  summarize_session: 20,
}

const LEVELS = [
  { name: 'Intern', minXp: 0 },
  { name: 'Resident', minXp: 100 },
  { name: 'Fellow', minXp: 300 },
  { name: 'Attending', minXp: 600 },
  { name: 'Chief', minXp: 1000 },
] as const

export function useGamification() {
  function xpForTool(toolName: string): number {
    return XP_TABLE[toolName] ?? 0
  }

  function getLevel(totalXp: number) {
    let current = LEVELS[0]
    let next = LEVELS[1]

    for (let i = LEVELS.length - 1; i >= 0; i--) {
      if (totalXp >= LEVELS[i].minXp) {
        current = LEVELS[i]
        next = LEVELS[i + 1] ?? null
        break
      }
    }

    const progress = next
      ? (totalXp - current.minXp) / (next.minXp - current.minXp)
      : 1

    return {
      name: current.name,
      minXp: current.minXp,
      nextLevel: next?.name ?? null,
      nextMinXp: next?.minXp ?? null,
      progress: Math.min(progress, 1),
    }
  }

  function computeXpFromStats(stats: Array<{ tool_name: string; count: number }>) {
    let total = 0
    for (const s of stats) {
      total += xpForTool(s.tool_name) * s.count
    }
    return total
  }

  return { xpForTool, getLevel, computeXpFromStats, XP_TABLE, LEVELS }
}
