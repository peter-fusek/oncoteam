/**
 * Stub for Nuxt auto-imports referenced by access-rights.ts and helpers
 * when unit-tested in isolation. The real Nuxt runtime provides these;
 * Vitest doesn't need them because we test pure functions.
 */
export const defineEventHandler = (fn: unknown) => fn
export const getRequestURL = (_event: unknown) => new URL('http://test/')
export const getUserSession = async () => ({ user: null })
export const replaceUserSession = async () => {}
export const clearUserSession = async () => {}
export const sendRedirect = (_event: unknown, url: string) => ({ __redirect: url })
export const createError = (opts: { statusCode: number, message: string }) => {
  const e: Error & { statusCode?: number } = new Error(opts.message)
  e.statusCode = opts.statusCode
  return e
}
export const useRuntimeConfig = () => ({})
export const $fetch = async () => ({})
