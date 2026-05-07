import { useRef, useEffect, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import type { RegionSummary } from '@/types/api'
import { availabilityColor, providerColor } from '@/lib/colors'

interface Props {
  regions: RegionSummary[]
  selectedRegion: string | null
  onRegionSelect: (region: RegionSummary) => void
}

const MAP_STYLE = 'https://demotiles.maplibre.org/style.json'

export function WorldMap({ regions, selectedRegion, onRegionSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<maplibregl.Marker[]>([])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    mapRef.current = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [20, 20],
      zoom: 1.5,
      attributionControl: false,
    })

    mapRef.current.addControl(new maplibregl.NavigationControl(), 'top-right')

    return () => {
      mapRef.current?.remove()
      mapRef.current = null
    }
  }, [])

  const clearMarkers = useCallback(() => {
    markersRef.current.forEach(m => m.remove())
    markersRef.current = []
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const addMarkers = () => {
      clearMarkers()

      regions.forEach(region => {
        const isSelected = region.region === selectedRegion
        const color = availabilityColor[region.best_availability]
        const border = providerColor[region.provider]

        const el = document.createElement('div')
        el.className = 'gpu-marker'
        el.style.cssText = [
          `width: ${isSelected ? '20px' : '14px'}`,
          `height: ${isSelected ? '20px' : '14px'}`,
          `border-radius: 50%`,
          `background: ${color}`,
          `border: 3px solid ${border}`,
          `cursor: pointer`,
          `box-shadow: 0 0 ${isSelected ? '12px' : '6px'} ${color}88`,
          `transition: all 0.2s ease`,
        ].join(';')

        el.title = `${region.display_region}\n$${region.best_price_per_gpu_hour}/GPU-hr`

        el.addEventListener('click', () => onRegionSelect(region))

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([region.longitude, region.latitude])
          .addTo(map)

        markersRef.current.push(marker)
      })
    }

    if (map.loaded()) {
      addMarkers()
    } else {
      map.once('load', addMarkers)
    }
  }, [regions, selectedRegion, clearMarkers, onRegionSelect])

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full rounded-xl overflow-hidden" />
      <div className="absolute bottom-4 left-4 bg-qumulo-panel/90 rounded-lg p-3 text-xs space-y-1">
        <p className="font-semibold text-gray-300 mb-2">Availability</p>
        {(['high', 'medium', 'low', 'unavailable'] as const).map(tier => (
          <div key={tier} className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full inline-block" style={{ background: availabilityColor[tier] }} />
            <span className="capitalize text-gray-400">{tier}</span>
          </div>
        ))}
        <p className="font-semibold text-gray-300 mt-3 mb-1">Provider border</p>
        {(['aws', 'azure', 'gcp'] as const).map(p => (
          <div key={p} className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full inline-block border-2" style={{ borderColor: providerColor[p], background: 'transparent' }} />
            <span className="uppercase text-gray-400">{p}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
