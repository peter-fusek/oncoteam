import { integer, pgTable, serial, text, timestamp } from 'drizzle-orm/pg-core'

export const gamificationStats = pgTable('gamification_stats', {
  id: serial('id').primaryKey(),
  totalXp: integer('total_xp').notNull().default(0),
  level: text('level').notNull().default('Intern'),
  lastActive: timestamp('last_active', { withTimezone: true }),
  streakDays: integer('streak_days').notNull().default(0),
  streakLastDate: text('streak_last_date'),
})

export const achievements = pgTable('achievements', {
  id: serial('id').primaryKey(),
  key: text('key').notNull().unique(),
  name: text('name').notNull(),
  description: text('description').notNull().default(''),
  unlockedAt: timestamp('unlocked_at', { withTimezone: true }),
})

export const xpLog = pgTable('xp_log', {
  id: serial('id').primaryKey(),
  toolName: text('tool_name').notNull(),
  xpEarned: integer('xp_earned').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
})

export const xpEvents = pgTable('xp_events', {
  id: serial('id').primaryKey(),
  agentId: text('agent_id').notNull().default('oncoteam'),
  xpAmount: integer('xp_amount').notNull(),
  sourceTool: text('source_tool').notNull(),
  sourceActivityId: text('source_activity_id'),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
})
