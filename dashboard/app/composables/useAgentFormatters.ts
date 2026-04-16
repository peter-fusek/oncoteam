export function useAgentFormatters() {
  function timeAgo(ts: string): string {
    if (!ts) return '-'
    const diff = Date.now() - new Date(ts).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  function formatDuration(ms: number): string {
    if (!ms) return '-'
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}m`
  }

  function formatCost(cost: number): string {
    return `$${(cost || 0).toFixed(4)}`
  }

  return { timeAgo, formatDuration, formatCost }
}
