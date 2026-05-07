import { useState } from 'react'
import { X, AlertTriangle, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import type { GPUSku, SpokeConfigProposal, WorkloadProfile } from '@/types/api'

interface Props {
  sku: GPUSku
  onClose: () => void
  onDeploy: (proposal: SpokeConfigProposal, extras: DeployExtras) => void
}

export interface DeployExtras {
  cdfNamespace: string
  jobScript: string
}

type Step = 'profile' | 'govern' | 'review'

const PROFILES: { value: WorkloadProfile; label: string; description: string }[] = [
  { value: 'ai_training',    label: 'AI Training',    description: 'Large model training — high throughput, large capacity' },
  { value: 'ai_inference',   label: 'AI Inference',   description: 'Serving — low latency, moderate capacity' },
  { value: 'hpc_simulation', label: 'HPC Simulation', description: 'Physics/CFD — very high throughput, large scratch' },
  { value: 'ngs_genomics',   label: 'NGS / Genomics', description: 'Read-heavy genomic pipelines' },
  { value: 'rendering',      label: 'Rendering',      description: 'Frame rendering — large asset storage, high IOPs' },
  { value: 'generic',        label: 'Generic',        description: 'General-purpose workload' },
]

export function ConfiguratorModal({ sku, onClose, onDeploy }: Props) {
  const [step, setStep] = useState<Step>('profile')
  const [profile, setProfile] = useState<WorkloadProfile>('ai_training')
  const [gpuCount, setGpuCount] = useState(sku.gpu_count)
  const [datasetTb, setDatasetTb] = useState(10)
  const [lifetimeHours, setLifetimeHours] = useState<number | ''>('')
  const [priceCeiling, setPriceCeiling] = useState<number | ''>('')
  const [cdfNamespace, setCdfNamespace] = useState('default')
  const [jobScript, setJobScript] = useState('')
  const [proposal, setProposal] = useState<SpokeConfigProposal | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchProposal = async () => {
    setLoading(true)
    setError(null)
    try {
      const p = await api.configurator.propose({
        provider: sku.provider,
        region: sku.region,
        sku_id: sku.sku_id,
        workload_profile: profile,
        gpu_count: gpuCount,
        dataset_size_tb: datasetTb,
        ephemeral_lifetime_hours: lifetimeHours !== '' ? lifetimeHours : undefined,
        price_ceiling_usd: priceCeiling !== '' ? priceCeiling : undefined,
      })
      setProposal(p)
      setStep('review')
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-qumulo-panel border border-qumulo-border rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-qumulo-border">
          <div>
            <h2 className="font-semibold text-white">Spoke + Compute Configurator</h2>
            <p className="text-xs text-gray-400">{sku.display_region} · {sku.gpu_count}× {sku.gpu_family.toUpperCase()}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white p-1">
            <X size={18} />
          </button>
        </div>

        {/* Steps */}
        <div className="flex px-6 pt-4 gap-6 text-xs">
          {(['profile', 'govern', 'review'] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <span className={[
                'w-5 h-5 rounded-full flex items-center justify-center font-semibold text-xs',
                step === s ? 'bg-qumulo-teal text-white' : 'bg-qumulo-border text-gray-400',
              ].join(' ')}>{i + 1}</span>
              <span className={step === s ? 'text-white' : 'text-gray-500'}>
                {s === 'profile' ? 'Profile' : s === 'govern' ? 'Govern' : 'Review'}
              </span>
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {step === 'profile' && (
            <>
              <label className="block">
                <span className="text-xs text-gray-400">Workload Profile</span>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {PROFILES.map(p => (
                    <button
                      key={p.value}
                      onClick={() => setProfile(p.value)}
                      className={[
                        'text-left p-3 rounded-lg border transition-colors',
                        profile === p.value
                          ? 'border-qumulo-teal bg-qumulo-teal/10'
                          : 'border-qumulo-border hover:border-qumulo-teal/40',
                      ].join(' ')}
                    >
                      <p className="text-xs font-medium text-white">{p.label}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{p.description}</p>
                    </button>
                  ))}
                </div>
              </label>

              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-xs text-gray-400">GPU Count</span>
                  <input
                    type="number" min={1} max={sku.gpu_count * 16} value={gpuCount}
                    onChange={e => setGpuCount(Number(e.target.value))}
                    className="mt-1 w-full bg-qumulo-dark border border-qumulo-border rounded px-3 py-2 text-sm text-white"
                  />
                </label>
                <label className="block">
                  <span className="text-xs text-gray-400">Dataset Size (TB)</span>
                  <input
                    type="number" min={0} step={0.5} value={datasetTb}
                    onChange={e => setDatasetTb(Number(e.target.value))}
                    className="mt-1 w-full bg-qumulo-dark border border-qumulo-border rounded px-3 py-2 text-sm text-white"
                  />
                </label>
              </div>
            </>
          )}

          {step === 'govern' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-xs text-gray-400">Ephemeral Lifetime (hours)</span>
                  <input
                    type="number" min={1} placeholder="No limit"
                    value={lifetimeHours}
                    onChange={e => setLifetimeHours(e.target.value ? Number(e.target.value) : '')}
                    className="mt-1 w-full bg-qumulo-dark border border-qumulo-border rounded px-3 py-2 text-sm text-white"
                  />
                </label>
                <label className="block">
                  <span className="text-xs text-gray-400">Price Ceiling (USD)</span>
                  <input
                    type="number" min={0} step={10} placeholder="No limit"
                    value={priceCeiling}
                    onChange={e => setPriceCeiling(e.target.value ? Number(e.target.value) : '')}
                    className="mt-1 w-full bg-qumulo-dark border border-qumulo-border rounded px-3 py-2 text-sm text-white"
                  />
                </label>
              </div>
              <label className="block">
                <span className="text-xs text-gray-400">CDF Namespace</span>
                <input
                  value={cdfNamespace}
                  onChange={e => setCdfNamespace(e.target.value)}
                  className="mt-1 w-full bg-qumulo-dark border border-qumulo-border rounded px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block">
                <span className="text-xs text-gray-400">Job Script (optional — triggers auto-submit)</span>
                <textarea
                  rows={4} value={jobScript}
                  onChange={e => setJobScript(e.target.value)}
                  placeholder="#!/bin/bash&#10;srun python train.py"
                  className="mt-1 w-full bg-qumulo-dark border border-qumulo-border rounded px-3 py-2 text-xs text-white font-mono"
                />
              </label>
            </>
          )}

          {step === 'review' && proposal && (
            <>
              <div className="grid grid-cols-2 gap-3 text-xs">
                {[
                  ['Spoke Nodes', proposal.spoke_node_count],
                  ['Spoke Capacity', `${proposal.spoke_capacity_tb} TB`],
                  ['Throughput', `${proposal.spoke_throughput_gbps} Gbps`],
                  ['HPC Orchestrator', proposal.hpc_orchestrator],
                  ['Cost / Hour', `$${proposal.estimated_cost_per_hour.toFixed(2)}`],
                  ['Est. Total', proposal.estimated_total_cost_usd != null ? `$${proposal.estimated_total_cost_usd.toLocaleString()}` : 'Open-ended'],
                ].map(([k, v]) => (
                  <div key={String(k)} className="bg-qumulo-dark rounded p-3 border border-qumulo-border">
                    <p className="text-gray-500">{k}</p>
                    <p className="text-white font-semibold mt-0.5">{String(v)}</p>
                  </div>
                ))}
              </div>

              {proposal.warnings.length > 0 && (
                <div className="space-y-2">
                  {proposal.warnings.map((w, i) => (
                    <div key={i} className="flex gap-2 bg-yellow-900/20 border border-yellow-700/40 rounded p-3 text-xs text-yellow-300">
                      <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                      <p>{w}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-700/40 rounded p-3">{error}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-qumulo-border">
          <button
            onClick={() => setStep(step === 'govern' ? 'profile' : 'profile')}
            className="text-xs text-gray-400 hover:text-white"
            disabled={step === 'profile'}
          >
            Back
          </button>
          <div className="flex gap-2">
            {step === 'profile' && (
              <button
                onClick={() => setStep('govern')}
                className="px-4 py-2 bg-qumulo-teal text-white rounded text-sm font-medium hover:bg-qumulo-teal/80 transition-colors"
              >
                Next: Governance →
              </button>
            )}
            {step === 'govern' && (
              <button
                onClick={fetchProposal}
                disabled={loading}
                className="px-4 py-2 bg-qumulo-teal text-white rounded text-sm font-medium hover:bg-qumulo-teal/80 transition-colors disabled:opacity-50"
              >
                {loading ? 'Calculating…' : 'Review Proposal →'}
              </button>
            )}
            {step === 'review' && proposal && (
              <button
                onClick={() => onDeploy(proposal, { cdfNamespace, jobScript })}
                className="px-4 py-2 bg-green-600 text-white rounded text-sm font-medium hover:bg-green-500 transition-colors flex items-center gap-2"
              >
                <CheckCircle size={14} />
                Deploy Spoke
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
