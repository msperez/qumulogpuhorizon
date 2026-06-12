import type { AvailabilityTier, CloudProvider, GPUFamily, PriceBand, PricingType } from '@/types/api'

export interface Filters {
  providers: CloudProvider[]
  gpuFamilies: GPUFamily[]
  priceBands: PriceBand[]
  pricingTypes: PricingType[]
  availabilityTiers: AvailabilityTier[]
  sovereigntyZones: string[]
}

interface Props {
  filters: Filters
  onChange: (filters: Filters) => void
}

function Toggle<T extends string>({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  selected: T[]
  onChange: (next: T[]) => void
}) {
  const toggle = (v: T) => {
    onChange(selected.includes(v) ? selected.filter(x => x !== v) : [...selected, v])
  }
  return (
    <div className="mb-4">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map(o => (
          <button
            key={o.value}
            onClick={() => toggle(o.value)}
            className={[
              'px-2 py-1 rounded text-xs font-medium border transition-colors',
              selected.includes(o.value)
                ? 'bg-qumulo-teal border-qumulo-teal text-white'
                : 'border-qumulo-border text-gray-400 hover:border-qumulo-teal/60',
            ].join(' ')}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

const PROVIDERS: { value: CloudProvider; label: string }[] = [
  { value: 'aws', label: 'AWS' },
  { value: 'azure', label: 'Azure' },
  { value: 'gcp', label: 'GCP' },
]

const GPU_FAMILIES: { value: GPUFamily; label: string }[] = [
  { value: 'h200',    label: 'H200' },
  { value: 'h100',    label: 'H100' },
  { value: 'a100',    label: 'A100' },
  { value: 'rtx6000', label: 'RTX 6000' },
  { value: 'l40s',    label: 'L40S' },
  { value: 'a10g',    label: 'A10G' },
  { value: 'l4',      label: 'L4' },
  { value: 't4',      label: 'T4' },
]

const PRICE_BANDS: { value: PriceBand; label: string }[] = [
  { value: 'economy', label: 'Economy <$1' },
  { value: 'standard', label: 'Standard $1–5' },
  { value: 'premium', label: 'Premium $5–15' },
  { value: 'ultra', label: 'Ultra >$15' },
]

const PRICING_TYPES: { value: PricingType; label: string }[] = [
  { value: 'on_demand',      label: 'On-Demand' },
  { value: 'spot',           label: 'Spot' },
  { value: 'capacity_block', label: 'Cap Block' },
  { value: 'committed_use',  label: 'Committed' },
]

const AVAILABILITY: { value: AvailabilityTier; label: string }[] = [
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

const EMPTY: Filters = {
  providers: [],
  gpuFamilies: [],
  priceBands: [],
  pricingTypes: [],
  availabilityTiers: [],
  sovereigntyZones: [],
}

export function FilterSidebar({ filters, onChange }: Props) {
  return (
    <aside className="w-60 shrink-0 bg-qumulo-panel border-r border-qumulo-border p-4 overflow-y-auto">
      <h2 className="text-sm font-semibold text-white mb-4">Filters</h2>

      <Toggle
        label="Cloud Provider"
        options={PROVIDERS}
        selected={filters.providers}
        onChange={providers => onChange({ ...filters, providers })}
      />
      <Toggle
        label="GPU Family"
        options={GPU_FAMILIES}
        selected={filters.gpuFamilies}
        onChange={gpuFamilies => onChange({ ...filters, gpuFamilies })}
      />
      <Toggle
        label="Capacity Type"
        options={PRICING_TYPES}
        selected={filters.pricingTypes}
        onChange={pricingTypes => onChange({ ...filters, pricingTypes })}
      />
      <Toggle
        label="Price Band"
        options={PRICE_BANDS}
        selected={filters.priceBands}
        onChange={priceBands => onChange({ ...filters, priceBands })}
      />
      <Toggle
        label="Availability"
        options={AVAILABILITY}
        selected={filters.availabilityTiers}
        onChange={availabilityTiers => onChange({ ...filters, availabilityTiers })}
      />

      <div className="mt-2">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Sovereignty
        </p>
        <input
          className="w-full bg-qumulo-dark border border-qumulo-border rounded px-2 py-1.5 text-xs text-gray-300 placeholder:text-gray-600"
          placeholder="e.g. EU, US, DE"
          value={filters.sovereigntyZones.join(', ')}
          onChange={e =>
            onChange({
              ...filters,
              sovereigntyZones: e.target.value
                .split(',')
                .map(s => s.trim())
                .filter(Boolean),
            })
          }
        />
      </div>

      <button
        className="mt-4 w-full text-xs text-gray-500 hover:text-gray-300 transition-colors"
        onClick={() => onChange(EMPTY)}
      >
        Clear all filters
      </button>
    </aside>
  )
}
