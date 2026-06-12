export type CloudProvider = 'aws' | 'azure' | 'gcp'
export type GPUFamily = 'a100' | 'h100' | 'h200' | 'a10g' | 'l40s' | 'l4' | 'rtx6000' | 'v100' | 't4' | 'mi300x'
export type AvailabilityTier = 'high' | 'medium' | 'low' | 'unavailable'
export type PriceBand = 'economy' | 'standard' | 'premium' | 'ultra'
export type PricingType = 'on_demand' | 'spot' | 'capacity_block' | 'committed_use'
export type WorkloadProfile =
  | 'ai_training'
  | 'ai_inference'
  | 'hpc_simulation'
  | 'ngs_genomics'
  | 'rendering'
  | 'generic'
export type DeploymentPhase =
  | 'pending'
  | 'provisioning_compute'
  | 'bootstrapping_spoke'
  | 'attaching_cdf'
  | 'registering_hpc'
  | 'submitting_job'
  | 'running'
  | 'draining'
  | 'destroying'
  | 'completed'
  | 'failed'

export interface RegionSummary {
  provider: CloudProvider
  region: string
  display_region: string
  latitude: number
  longitude: number
  best_availability: AvailabilityTier
  best_price_per_gpu_hour: number
  price_band: PriceBand
  gpu_families: GPUFamily[]
  sku_count: number
  refreshed_at: string
  staleness_seconds: number
}

export interface GPUSku {
  sku_id: string
  provider: CloudProvider
  region: string
  display_region: string
  gpu_family: GPUFamily
  gpu_count: number
  vcpus: number
  memory_gb: number
  gpu_memory_gb: number
  interconnect: string | null
  pricing_type: PricingType
  price_per_gpu_hour: number
  price_band: PriceBand
  availability: AvailabilityTier
  available_count: number | null
  latitude: number
  longitude: number
  sovereignty_zones: string[]
  refreshed_at: string
  staleness_seconds: number
}

export interface GPUCatalogResponse {
  generated_at: string
  total_regions: number
  total_skus: number
  regions: RegionSummary[]
}

export interface GPUSkuListResponse {
  generated_at: string
  region: string
  provider: CloudProvider
  skus: GPUSku[]
}

export interface SpokeConfigRequest {
  provider: CloudProvider
  region: string
  sku_id: string
  workload_profile: WorkloadProfile
  gpu_count: number
  dataset_size_tb: number
  ephemeral_lifetime_hours?: number
  price_ceiling_usd?: number
}

export interface SpokeConfigProposal {
  provider: CloudProvider
  region: string
  sku_id: string
  workload_profile: WorkloadProfile
  gpu_count: number
  spoke_node_count: number
  spoke_capacity_tb: number
  spoke_throughput_gbps: number
  estimated_cost_per_hour: number
  estimated_total_cost_usd: number | null
  estimated_egress_cost_usd: number | null
  hpc_orchestrator: string
  warnings: string[]
}

export interface DeploymentEvent {
  timestamp: string
  phase: DeploymentPhase
  message: string
  detail: Record<string, unknown> | null
}

export interface Deployment {
  deployment_id: string
  request: {
    provider: CloudProvider
    region: string
    sku_id: string
    gpu_count: number
    workload_profile: WorkloadProfile
    spoke_node_count: number
    spoke_capacity_tb: number
    hpc_orchestrator: string
    cdf_namespace: string
    ephemeral_lifetime_hours: number | null
    price_ceiling_usd: number | null
    operator_id: string
  }
  phase: DeploymentPhase
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  teardown_reason: string | null
  events: DeploymentEvent[]
  spoke_cluster_id: string | null
  compute_stack_id: string | null
  hpc_environment_id: string | null
  job_id: string | null
  current_cost_usd: number
  error: string | null
}

export interface DeploymentCostSummary {
  deployment_id: string
  provider: string
  region: string
  started_at: string | null
  updated_at: string
  phase: string
  runtime_hours: number
  cost_per_hour_usd: number
  current_cost_usd: number
  price_ceiling_usd: number | null
  ceiling_pct_consumed: number | null
  lifetime_hours: number | null
  lifetime_remaining_hours: number | null
  teardown_triggered: boolean
  teardown_reason: string | null
}
