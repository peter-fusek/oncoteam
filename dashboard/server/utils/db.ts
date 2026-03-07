import { drizzle } from 'drizzle-orm/postgres-js'
import postgres from 'postgres'
import * as schema from '../db/schema'

let _db: ReturnType<typeof drizzle> | null = null

export function useDb() {
  if (_db) return _db

  const config = useRuntimeConfig()
  const databaseUrl = config.databaseUrl

  if (!databaseUrl) {
    throw new Error('DATABASE_URL is not configured')
  }

  const isExternal = databaseUrl.includes('.render.com')
  const client = postgres(databaseUrl, isExternal ? { ssl: 'require' } : {})
  _db = drizzle(client, { schema })
  return _db
}
