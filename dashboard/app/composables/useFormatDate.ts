export function useFormatDate() {
  const { locale } = useI18n()

  function formatDate(dateStr: string | null | undefined): string {
    if (!dateStr) return ''
    const [y, m, d] = dateStr.slice(0, 10).split('-')
    if (!y || !m || !d) return dateStr
    return locale.value === 'sk' ? `${d}.${m}.${y}` : `${y}-${m}-${d}`
  }

  function formatDateShort(dateStr: string | null | undefined): string {
    if (!dateStr) return ''
    const [, m, d] = dateStr.slice(0, 10).split('-')
    if (!m || !d) return dateStr
    return locale.value === 'sk' ? `${d}.${m}.` : `${m}-${d}`
  }

  return { formatDate, formatDateShort }
}
