import { writeHeapSnapshot } from 'node:v8'
import { stat, unlink } from 'node:fs/promises'
import { createReadStream } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// On-demand V8 heap snapshot for diagnosing the OAuth-flow memory retain (#447).
// Guarded by NUXT_HEAP_DUMP_KEY env var; if the env var is unset the endpoint
// fails closed with 503 (no key configured = endpoint disabled). The snapshot
// is written to a temp file and streamed as an attachment, then deleted.
//
// Usage: capture pre-trigger and post-trigger snapshots, diff in Chrome DevTools
// (Memory → Load → Comparison view) and sort by Delta to name the retain class.
//   curl -H "X-Heap-Dump-Key: $KEY" https://.../api/internal/heapdump -o pre.heapsnapshot
//   <trigger the suspected leak>
//   curl -H "X-Heap-Dump-Key: $KEY" https://.../api/internal/heapdump -o post.heapsnapshot
export default defineEventHandler(async (event) => {
  const expected = process.env.NUXT_HEAP_DUMP_KEY
  if (!expected) {
    throw createError({ statusCode: 503, message: 'Heap dump endpoint disabled (NUXT_HEAP_DUMP_KEY not set)' })
  }

  const provided = getHeader(event, 'x-heap-dump-key') || (getQuery(event).key as string | undefined)
  if (provided !== expected) {
    throw createError({ statusCode: 401, message: 'Invalid heap dump key' })
  }

  const filename = `heap-${Date.now()}-${process.pid}.heapsnapshot`
  const filepath = join(tmpdir(), filename)

  // writeHeapSnapshot is synchronous and blocks the event loop while V8 walks
  // the heap (seconds, not ms, for multi-GB heaps). Acceptable for this use.
  writeHeapSnapshot(filepath)

  const stats = await stat(filepath)
  setHeader(event, 'Content-Type', 'application/octet-stream')
  setHeader(event, 'Content-Disposition', `attachment; filename="${filename}"`)
  setHeader(event, 'Content-Length', String(stats.size))

  const stream = createReadStream(filepath)
  stream.on('close', () => {
    unlink(filepath).catch(() => { /* best effort cleanup */ })
  })
  return sendStream(event, stream)
})
