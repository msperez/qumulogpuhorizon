import { useState } from 'react'
import { WorldMap } from '@/components/WorldMap'
import { FilterSidebar, type Filters } from '@/components/FilterSidebar'
import { RegionPanel } from '@/components/RegionPanel'
import { ConfiguratorModal, type DeployExtras } from '@/components/ConfiguratorModal'
import { useCatalog } from '@/hooks/useCatalog'
import type { GPUSku, RegionSummary, SpokeConfigProposal } from '@/types/api'
import { api } from '@/lib/api'

export function DiscoverPage() {
  const [filters, setFilters] = useState<Filters>({
    providers: [],
    gpuFamilies: [],
    priceBands: [],
    pricingTypes: [],
    availabilityTiers: [],
    sovereigntyZones: [],
  })
  const [selectedRegion, setSelectedRegion] = useState<RegionSummary | null>(null)
  const [configuringSku, setConfiguringSku] = useState<GPUSku | null>(null)
  const [deployToast, setDeployToast] = useState<string | null>(null)

  const { data, loading } = useCatalog()

  const filteredRegions = (data?.regions ?? []).filter(r => {
    if (filters.providers.length && !filters.providers.includes(r.provider)) return false
    if (filters.gpuFamilies.length && !r.gpu_families.some(f => filters.gpuFamilies.includes(f))) return false
    if (filters.priceBands.length && !filters.priceBands.includes(r.price_band)) return false
    if (filters.availabilityTiers.length && !filters.availabilityTiers.includes(r.best_availability)) return false
    if (filters.sovereigntyZones.length) {
      // region summaries don't carry zones; filtering happens server-side via API
    }
    return true
  })

  const handleDeploy = async (proposal: SpokeConfigProposal, extras: DeployExtras) => {
    if (!configuringSku) return
    try {
      const dep = await api.deployments.create({
        provider: configuringSku.provider,
        region: configuringSku.region,
        sku_id: configuringSku.sku_id,
        gpu_count: proposal.gpu_count,
        workload_profile: proposal.workload_profile,
        spoke_node_count: proposal.spoke_node_count,
        spoke_capacity_tb: proposal.spoke_capacity_tb,
        hpc_orchestrator: proposal.hpc_orchestrator.toLowerCase().replace(/ /g, '_'),
        cdf_namespace: extras.cdfNamespace,
        ephemeral_lifetime_hours: proposal.estimated_total_cost_usd ? undefined : undefined,
        price_ceiling_usd: proposal.estimated_total_cost_usd ?? undefined,
        job_script: extras.jobScript || undefined,
        operator_id: 'operator@qumulo.internal',
      })
      setConfiguringSku(null)
      setSelectedRegion(null)
      setDeployToast(`Deployment ${dep.deployment_id.slice(0, 8)} started — check the Dashboard.`)
      setTimeout(() => setDeployToast(null), 6000)
    } catch (e) {
      alert('Deployment failed: ' + String(e))
    }
  }

  return (
    <div className="flex-1 flex overflow-hidden relative">
      <FilterSidebar filters={filters} onChange={setFilters} />

      {/* Map area */}
      <div className="flex-1 flex flex-col">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-qumulo-dark/50 z-10">
            <div className="text-gray-400 text-sm">Loading GPU catalog…</div>
          </div>
        )}

        <div className="flex-1 p-4">
          <WorldMap
            regions={filteredRegions}
            selectedRegion={selectedRegion?.region ?? null}
            onRegionSelect={setSelectedRegion}
          />
        </div>

        {/* Stats bar */}
        {data && (
          <div className="px-4 pb-3 flex gap-4 text-xs text-gray-500">
            <span>{data.total_regions} regions</span>
            <span>·</span>
            <span>{data.total_skus} SKUs</span>
            {filteredRegions.length < data.total_regions && (
              <>
                <span>·</span>
                <span className="text-qumulo-teal">{filteredRegions.length} visible with filters</span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Region side panel */}
      {selectedRegion && (
        <RegionPanel
          region={selectedRegion}
          onClose={() => setSelectedRegion(null)}
          onConfigure={setConfiguringSku}
        />
      )}

      {/* Configurator modal */}
      {configuringSku && (
        <ConfiguratorModal
          sku={configuringSku}
          onClose={() => setConfiguringSku(null)}
          onDeploy={handleDeploy}
        />
      )}

      {/* Success toast */}
      {deployToast && (
        <div className="absolute bottom-6 right-6 bg-green-800 border border-green-600 text-green-200 text-sm rounded-lg px-4 py-3 shadow-xl">
          {deployToast}
        </div>
      )}
    </div>
  )
}
