import { useEffect, useState } from 'react'
import { Activity, DollarSign, Clock, Trash2, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import type { Deployment, DeploymentCostSummary } from '@/types/api'
import { phaseLabel, providerColor } from '@/lib/colors'

const REFRESH_MS = 10_000

interface PhaseStepProps {
  phase: string
  current: string
}

const PHASES = [
  'provisioning_compute',
  'bootstrapping_spoke',
  'attaching_cdf',
  'registering_hpc',
  'running',
]

function PhaseProgress({ current }: PhaseStepProps) {
  const currentIdx = PHASES.indexOf(current)
  return (
    <div className="flex items-center gap-1 mt-2">
      {PHASES.map((p, i) => {
        const done = i < currentIdx
        const active = i === currentIdx
        return (
          <div key={p} className="flex items-center gap-1 flex-1">
            <div className={[
              'h-1 flex-1 rounded-full transition-colors',
              done ? 'bg-qumulo-teal' : active ? 'bg-qumulo-teal/50 animate-pulse' : 'bg-qumulo-border',
            ].join(' ')} />
          </div>
        )
      })}
    </div>
  )
}

function DeploymentCard({ deployment, cost }: { deployment: Deployment; cost?: DeploymentCostSummary }) {
  const [tearingDown, setTearingDown] = useState(false)

  const handleTeardown = async () => {
    if (!confirm(`Tear down deployment ${deployment.deployment_id.slice(0, 8)}?`)) return
    setTearingDown(true)
    try {
      await api.deployments.teardown(deployment.deployment_id)
    } catch (e) {
      alert(String(e))
      setTearingDown(false)
    }
  }

  const isActive = !['completed', 'failed'].includes(deployment.phase)
  const isFailed = deployment.phase === 'failed'

  return (
    <div className={[
      'bg-qumulo-panel border rounded-lg p-4 space-y-3',
      isFailed ? 'border-red-700/50' : 'border-qumulo-border',
    ].join(' ')}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="text-xs font-semibold uppercase px-1.5 py-0.5 rounded"
              style={{ background: providerColor[deployment.request.provider] + '22', color: providerColor[deployment.request.provider] }}
            >
              {deployment.request.provider}
            </span>
            <span className="text-sm font-medium text-white">{deployment.request.region}</span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            {deployment.request.gpu_count}× GPU · {deployment.request.workload_profile.replace('_', ' ')}
          </p>
          <p className="text-xs text-gray-600 font-mono">{deployment.deployment_id.slice(0, 8)}</p>
        </div>

        <div className="text-right">
          <p className={[
            'text-xs font-semibold',
            deployment.phase === 'running' ? 'text-green-400' : isFailed ? 'text-red-400' : 'text-yellow-400',
          ].join(' ')}>
            {phaseLabel[deployment.phase] ?? deployment.phase}
          </p>
          {cost && (
            <p className="text-xs text-gray-400 mt-0.5">${cost.current_cost_usd.toFixed(2)}</p>
          )}
        </div>
      </div>

      {isActive && !isFailed && (
        <PhaseProgress phase={deployment.phase} current={deployment.phase} />
      )}

      {/* Cost bar */}
      {cost?.price_ceiling_usd && (
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Price ceiling</span>
            <span>{cost.ceiling_pct_consumed?.toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-qumulo-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.min(100, cost.ceiling_pct_consumed ?? 0)}%`,
                background: (cost.ceiling_pct_consumed ?? 0) > 80 ? '#ef4444' : '#0057b8',
              }}
            />
          </div>
        </div>
      )}

      {/* Lifetime countdown */}
      {cost?.lifetime_remaining_hours != null && (
        <div className="flex items-center gap-1.5 text-xs text-yellow-400">
          <Clock size={11} />
          <span>{cost.lifetime_remaining_hours.toFixed(1)}h remaining</span>
        </div>
      )}

      {/* Teardown warning */}
      {cost?.teardown_triggered && (
        <div className="flex items-center gap-1.5 text-xs text-orange-400">
          <AlertTriangle size={11} />
          <span>Teardown triggered: {cost.teardown_reason}</span>
        </div>
      )}

      {isFailed && deployment.error && (
        <p className="text-xs text-red-400 bg-red-900/20 rounded p-2">{deployment.error}</p>
      )}

      {/* Deployment details */}
      {deployment.phase === 'running' && (
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
          {deployment.spoke_cluster_id && (
            <div>Spoke: <span className="text-gray-300 font-mono">{deployment.spoke_cluster_id}</span></div>
          )}
          {deployment.hpc_environment_id && (
            <div>HPC: <span className="text-gray-300 font-mono">{deployment.hpc_environment_id}</span></div>
          )}
        </div>
      )}

      {isActive && (
        <button
          onClick={handleTeardown}
          disabled={tearingDown}
          className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
        >
          <Trash2 size={11} />
          {tearingDown ? 'Tearing down…' : 'Manual teardown'}
        </button>
      )}
    </div>
  )
}

export function Dashboard() {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [costs, setCosts] = useState<Record<string, DeploymentCostSummary>>({})
  const [loading, setLoading] = useState(true)

  const fetchData = () => {
    Promise.all([
      api.deployments.list(),
      api.cost.list(),
    ]).then(([deps, costList]) => {
      setDeployments(deps.deployments)
      const costMap: Record<string, DeploymentCostSummary> = {}
      costList.forEach(c => { costMap[c.deployment_id] = c })
      setCosts(costMap)
    }).catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
    const t = setInterval(fetchData, REFRESH_MS)
    return () => clearInterval(t)
  }, [])

  const running = deployments.filter(d => d.phase === 'running').length
  const totalCost = Object.values(costs).reduce((s, c) => s + c.current_cost_usd, 0)

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-white">Operations Dashboard</h1>
          <button onClick={fetchData} className="text-xs text-gray-400 hover:text-white transition-colors">
            Refresh
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { icon: Activity, label: 'Active Deployments', value: running, color: 'text-green-400' },
            { icon: DollarSign, label: 'Total Running Cost', value: `$${totalCost.toFixed(2)}`, color: 'text-yellow-400' },
            { icon: Clock, label: 'Total Deployments', value: deployments.length, color: 'text-blue-400' },
          ].map(({ icon: Icon, label, value, color }) => (
            <div key={label} className="bg-qumulo-panel border border-qumulo-border rounded-lg p-4 flex items-center gap-3">
              <Icon size={20} className={color} />
              <div>
                <p className="text-xs text-gray-400">{label}</p>
                <p className={`text-lg font-semibold ${color}`}>{value}</p>
              </div>
            </div>
          ))}
        </div>

        {loading && <p className="text-gray-500 text-sm text-center py-8">Loading deployments…</p>}

        {!loading && deployments.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <Activity size={40} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">No deployments yet. Select a region on the map to get started.</p>
          </div>
        )}

        <div className="space-y-4">
          {deployments.map(d => (
            <DeploymentCard key={d.deployment_id} deployment={d} cost={costs[d.deployment_id]} />
          ))}
        </div>
      </div>
    </div>
  )
}
