import type { AvailabilityTier, PriceBand } from '@/types/api'

export const availabilityColor: Record<AvailabilityTier, string> = {
  high:        '#22c55e',   // green-500
  medium:      '#eab308',   // yellow-500
  low:         '#f97316',   // orange-500
  unavailable: '#6b7280',   // gray-500
}

export const priceBandColor: Record<PriceBand, string> = {
  economy:  '#22d3ee',  // cyan-400
  standard: '#818cf8',  // indigo-400
  premium:  '#f59e0b',  // amber-500
  ultra:    '#ef4444',  // red-500
}

export const providerColor = {
  aws:   '#ff9900',
  azure: '#0078d4',
  gcp:   '#34a853',
} as const

export const phaseLabel: Record<string, string> = {
  pending:               'Pending',
  provisioning_compute:  'Provisioning Compute',
  bootstrapping_spoke:   'Bootstrapping Spoke',
  attaching_cdf:         'Attaching CDF Namespace',
  registering_hpc:       'Registering HPC Orchestrator',
  submitting_job:        'Submitting Job',
  running:               'Running',
  draining:              'Draining',
  destroying:            'Destroying',
  completed:             'Completed',
  failed:                'Failed',
}
