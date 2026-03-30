export interface DrilldownItem {
  type: string
  id: string | number
  label: string
  data?: Record<string, unknown>
}

interface DetailResponse {
  type: string
  id: string | number
  data: Record<string, unknown>
  source: {
    oncofiles_id: number | null
    gdrive_file_id: string | null
    gdrive_url: string | null
  }
  related: Array<{ type: string; id: string | number; label: string }>
}

export function useDrilldown() {
  const isOpen = useState('drilldown-open', () => false)
  const stack = useState<DrilldownItem[]>('drilldown-stack', () => [])
  const detail = useState<DetailResponse | null>('drilldown-detail', () => null)
  const loading = useState('drilldown-loading', () => false)
  const error = useState<string | null>('drilldown-error', () => null)
  const current = computed(() => stack.value.length ? stack.value[stack.value.length - 1] : null)

  async function fetchDetail(item: DrilldownItem) {
    if (item.data) {
      detail.value = {
        type: item.type,
        id: item.id,
        data: item.data,
        source: { oncofiles_id: null, gdrive_file_id: null, gdrive_url: null },
        related: [],
      }
      return
    }

    loading.value = true
    error.value = null
    try {
      const { activePatientId } = useActivePatient()
      const pid = activePatientId.value || 'erika'
      const result = await $fetch<DetailResponse>(`/api/oncoteam/detail/${item.type}/${item.id}?patient_id=${pid}`)
      detail.value = result
    } catch (e: any) {
      error.value = e.message || String(e)
      detail.value = null
    } finally {
      loading.value = false
    }
  }

  async function open(item: DrilldownItem) {
    stack.value = [item]
    isOpen.value = true
    await fetchDetail(item)
  }

  async function push(item: DrilldownItem) {
    stack.value = [...stack.value, item]
    await fetchDetail(item)
  }

  function pop() {
    if (stack.value.length > 1) {
      stack.value = stack.value.slice(0, -1)
      const prev = stack.value[stack.value.length - 1]
      fetchDetail(prev)
    }
  }

  function popTo(index: number) {
    if (index < stack.value.length - 1) {
      stack.value = stack.value.slice(0, index + 1)
      const target = stack.value[stack.value.length - 1]
      fetchDetail(target)
    }
  }

  function close() {
    isOpen.value = false
    stack.value = []
    detail.value = null
    error.value = null
  }

  return { isOpen, stack, current, detail, loading, error, open, push, pop, popTo, close }
}
