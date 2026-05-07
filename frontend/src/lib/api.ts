import type {
  Deployment,
  DeploymentCostSummary,
  GPUCatalogResponse,
  GPUSkuListResponse,
  SpokeConfigProposal,
  SpokeConfigRequest,
  CloudProvider,
} from '@/types/api'

const BASE = '/api/v1'

async function get<T>(path: string, params?: Record<string, string | string[]>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    for (const [key, val] of Object.entries(params)) {
      if (Array.isArray(val)) {
        val.forEach(v => url.searchParams.append(key, v))
      } else {
        url.searchParams.set(key, val)
      }
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API POST ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

async function del<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'DELETE',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`API DELETE ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  catalog: {
    regions: (filters?: {
      provider?: string[]
      gpu_family?: string[]
      price_band?: string[]
      sovereignty_zone?: string[]
    }) => get<GPUCatalogResponse>('/regions', filters as Record<string, string[]>),

    regionSkus: (provider: CloudProvider, region: string) =>
      get<GPUSkuListResponse>(`/regions/${provider}/${region}/skus`),
  },

  configurator: {
    propose: (req: SpokeConfigRequest) =>
      post<SpokeConfigProposal>('/configure/spoke', req),
  },

  deployments: {
    list: () => get<{ deployments: Deployment[]; total: number }>('/deployments'),
    get: (id: string) => get<Deployment>(`/deployments/${id}`),
    create: (req: Record<string, unknown>) =>
      post<Deployment>('/deployments', req),
    teardown: (id: string, reason = 'manual') =>
      del<Deployment>(`/deployments/${id}`, { reason }),
  },

  cost: {
    list: () => get<DeploymentCostSummary[]>('/cost'),
    get: (id: string) => get<DeploymentCostSummary>(`/cost/${id}`),
  },
}
