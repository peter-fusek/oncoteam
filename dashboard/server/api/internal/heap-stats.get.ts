import { writeHeapSnapshot } from 'node:v8'
import { readFile, unlink, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Server-side heap-snapshot aggregator. Walks the snapshot in-process and
// returns just {constructor → count, total_size_bytes} as JSON. Returns ~5KB
// instead of 16+ MB raw .heapsnapshot, so it survives the network when the
// pod is under GC pressure and a streamed download would time out.
//
// Capture before AND after suspected-leak trigger; diff client-side. Written
// for #447 OAuth-flow retain investigation. Never exfiltrates raw memory.
//
// Usage:
//   curl -H "X-Heap-Dump-Key: $KEY" https://.../api/internal/heap-stats?top=50
export default defineEventHandler(async (event) => {
  const expected = process.env.NUXT_HEAP_DUMP_KEY
  if (!expected) {
    throw createError({ statusCode: 503, message: 'Heap stats endpoint disabled (NUXT_HEAP_DUMP_KEY not set)' })
  }
  const provided = getHeader(event, 'x-heap-dump-key') || (getQuery(event).key as string | undefined)
  if (provided !== expected) {
    throw createError({ statusCode: 401, message: 'Invalid heap dump key' })
  }

  const top = Math.min(Math.max(parseInt((getQuery(event).top as string) || '50', 10) || 50, 10), 500)
  const filename = `heap-stats-${Date.now()}-${process.pid}.heapsnapshot`
  const filepath = join(tmpdir(), filename)

  const writeStart = Date.now()
  writeHeapSnapshot(filepath)
  const writeDur = Date.now() - writeStart

  const stats = await stat(filepath)
  const parseStart = Date.now()
  const raw = await readFile(filepath, 'utf8')
  await unlink(filepath).catch(() => { /* best effort */ })

  const data = JSON.parse(raw)
  const meta = data.snapshot.meta
  const nodeFields: string[] = meta.node_fields
  const nodeTypes: string[][] = meta.node_types
  const nodes: number[] = data.nodes
  const strings: string[] = data.strings
  const typeIdx = nodeFields.indexOf('type')
  const nameIdx = nodeFields.indexOf('name')
  const sizeIdx = nodeFields.indexOf('self_size')
  const typeNames = nodeTypes[0]
  const nPer = nodeFields.length

  // Aggregate (typeName, constructor) → [count, totalSize]
  const byClass = new Map<string, { type: string; name: string; count: number; size: number }>()
  let totalCount = 0
  let totalSize = 0
  for (let i = 0; i < nodes.length; i += nPer) {
    const t = nodes[i + typeIdx]
    const n = nodes[i + nameIdx]
    const s = nodes[i + sizeIdx]
    const tn = typeNames[t] || `type_${t}`
    const cn = strings[n] || '?'
    const key = `${tn}\x00${cn}`
    let entry = byClass.get(key)
    if (!entry) {
      entry = { type: tn, name: cn, count: 0, size: 0 }
      byClass.set(key, entry)
    }
    entry.count++
    entry.size += s
    totalCount++
    totalSize += s
  }
  const parseDur = Date.now() - parseStart

  const all = Array.from(byClass.values())
  const topBySize = all.slice().sort((a, b) => b.size - a.size).slice(0, top)
  const topByCount = all.slice().sort((a, b) => b.count - a.count).slice(0, top)

  // Aggregate by type only
  const byType = new Map<string, { count: number; size: number }>()
  for (const e of all) {
    let t = byType.get(e.type)
    if (!t) { t = { count: 0, size: 0 }; byType.set(e.type, t) }
    t.count += e.count
    t.size += e.size
  }
  const byTypeArr = Array.from(byType.entries())
    .map(([type, v]) => ({ type, ...v }))
    .sort((a, b) => b.size - a.size)

  return {
    captured_at: new Date().toISOString(),
    pid: process.pid,
    snapshot_bytes: stats.size,
    write_duration_ms: writeDur,
    parse_duration_ms: parseDur,
    total_node_count: totalCount,
    total_self_size: totalSize,
    by_type: byTypeArr,
    top_by_size: topBySize.map(e => ({ type: e.type, name: e.name.slice(0, 200), count: e.count, size: e.size })),
    top_by_count: topByCount.map(e => ({ type: e.type, name: e.name.slice(0, 200), count: e.count, size: e.size })),
  }
})
