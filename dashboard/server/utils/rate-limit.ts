// Sweep expired entries from a per-key rate-limit Map. Without this the map
// grows without bound — every distinct phone/email that has ever posted adds
// a permanent entry (#447 Felix #4).
export function purgeExpiredRateLimitEntries(
  map: Map<string, { count: number; resetAt: number }>,
  now: number,
): void {
  for (const [key, entry] of map) {
    if (now >= entry.resetAt) map.delete(key)
  }
}
