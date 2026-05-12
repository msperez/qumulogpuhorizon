import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { GPUCatalogResponse, RegionSummary } from '@/types/api'

const REFRESH_MS = 60_000
const RETRY_MS = 5_000   // fast retry when data is absent or after an error

export function useCatalog() {
  const [data, setData] = useState<GPUCatalogResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const schedule = useCallback((ms: number) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(fetchData, ms)
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  function fetchData() {
    api.catalog.regions()
      .then(res => {
        setData(res)
        setError(null)
        // If catalog came back empty, retry faster
        schedule(res.total_skus === 0 ? RETRY_MS : REFRESH_MS)
      })
      .catch(e => {
        setError(String(e))
        schedule(RETRY_MS)   // retry quickly on error
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, error, refresh: fetchData }
}

export function useRegionSkus(provider: string | null, region: string | null) {
  const [data, setData] = useState<RegionSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!provider || !region) { setData(null); return }
    setLoading(true)
    api.catalog.regionSkus(provider as never, region)
      .then(() => setData(null))  // placeholder; component reads full SKU list
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [provider, region])

  return { data, loading, error }
}
