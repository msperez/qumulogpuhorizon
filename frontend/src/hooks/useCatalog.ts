import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { GPUCatalogResponse, RegionSummary } from '@/types/api'

const REFRESH_MS = 60_000

export function useCatalog() {
  const [data, setData] = useState<GPUCatalogResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = () => {
    api.catalog.regions()
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
    timerRef.current = setInterval(fetchData, REFRESH_MS)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  return { data, loading, error, refresh: fetchData }
}

export function useRegionSkus(provider: string | null, region: string | null) {
  const [data, setData] = useState<RegionSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!provider || !region) { setData(null); return }
    setLoading(true)
    // We pass provider/region typed correctly via cast since hook receives strings
    api.catalog.regionSkus(provider as never, region)
      .then(() => setData(null))  // placeholder; component reads full SKU list
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [provider, region])

  return { data, loading, error }
}
