import { useState, useEffect } from 'react'
import { X, Zap, HardDrive, DollarSign, Server } from 'lucide-react'
import { api } from '@/lib/api'
import type { GPUSku, RegionSummary } from '@/types/api'
import { availabilityColor, priceBandColor, providerColor } from '@/lib/colors'

interface Props {
  region: RegionSummary
  onClose: () => void
  onConfigure: (sku: GPUSku) => void
}

export function RegionPanel({ region, onClose, onConfigure }: Props) {
  const [skus, setSkus] = useState<GPUSku[]>([])
  const [loading, setLoading] = useState(true)
  const [pricingFilter, setPricingFilter] = useState<string>('all')

  useEffect(() => {
    setLoading(true)
    api.catalog.regionSkus(region.provider, region.region)
      .then(r => setSkus(r.skus))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [region.provider, region.region])

  const filtered = pricingFilter === 'all'
    ? skus
    : skus.filter(s => s.pricing_type === pricingFilter)

  return (
    <div className="w-96 bg-qumulo-panel border-l border-qumulo-border flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-qumulo-border">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-semibold text-white">{region.display_region}</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              <span style={{ color: providerColor[region.provider] }} className="uppercase font-medium">
                {region.provider}
              </span>
              {' · '}
              {region.region}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors p-1">
            <X size={16} />
          </button>
        </div>

        <div className="mt-3 flex gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: availabilityColor[region.best_availability] }} />
            <span className="capitalize text-gray-300">{region.best_availability}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <DollarSign size={11} className="text-gray-400" />
            <span className="text-gray-300">from ${region.best_price_per_gpu_hour}/GPU-hr</span>
          </div>
        </div>

        <div className="mt-3 flex gap-1">
          {(['all', 'on_demand', 'spot', 'committed_use'] as const).map(type => (
            <button
              key={type}
              onClick={() => setPricingFilter(type)}
              className={[
                'px-2 py-1 rounded text-xs transition-colors',
                pricingFilter === type
                  ? 'bg-qumulo-teal text-white'
                  : 'text-gray-400 hover:text-white',
              ].join(' ')}
            >
              {type === 'all' ? 'All' : type.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* SKU list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading && (
          <div className="text-center text-gray-500 text-sm py-8">Loading SKUs…</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="text-center text-gray-500 text-sm py-8">No SKUs match the selected filter.</div>
        )}
        {filtered.map(sku => (
          <div
            key={sku.sku_id}
            className="bg-qumulo-dark rounded-lg p-3 border border-qumulo-border hover:border-qumulo-teal/50 transition-colors group"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold text-white">{sku.gpu_count}× {sku.gpu_family.toUpperCase()}</p>
                <p className="text-xs text-gray-500">{sku.sku_id.split(':').slice(-2, -1)[0]}</p>
              </div>
              <span
                className="text-xs px-1.5 py-0.5 rounded font-medium"
                style={{ background: priceBandColor[sku.price_band] + '22', color: priceBandColor[sku.price_band] }}
              >
                ${sku.price_per_gpu_hour}/hr
              </span>
            </div>

            <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-400">
              <div className="flex items-center gap-1">
                <Zap size={10} />
                <span>{sku.vcpus} vCPU</span>
              </div>
              <div className="flex items-center gap-1">
                <HardDrive size={10} />
                <span>{sku.gpu_memory_gb}GB VRAM</span>
              </div>
              <div className="flex items-center gap-1">
                <Server size={10} />
                <span>{sku.available_count ?? '?'} avail</span>
              </div>
            </div>

            {sku.interconnect && (
              <p className="mt-1 text-xs text-qumulo-teal/70">{sku.interconnect}</p>
            )}

            <button
              onClick={() => onConfigure(sku)}
              className="mt-2 w-full text-xs py-1.5 rounded border border-qumulo-teal/40 text-qumulo-teal
                         hover:bg-qumulo-teal/10 transition-colors opacity-0 group-hover:opacity-100"
            >
              Configure Spoke →
            </button>
          </div>
        ))}
      </div>

      {region.staleness_seconds > 60 && (
        <div className="px-4 py-2 border-t border-qumulo-border text-xs text-yellow-500">
          Data is {Math.round(region.staleness_seconds / 60)}m old — pricing is advisory
        </div>
      )}
    </div>
  )
}
