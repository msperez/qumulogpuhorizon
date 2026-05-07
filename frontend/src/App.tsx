import { useState } from 'react'
import { Map, LayoutDashboard, Cpu } from 'lucide-react'
import { DiscoverPage } from '@/pages/DiscoverPage'
import { Dashboard } from '@/components/Dashboard'

type View = 'discover' | 'dashboard'

export default function App() {
  const [view, setView] = useState<View>('discover')

  return (
    <div className="h-screen flex flex-col bg-qumulo-dark text-white overflow-hidden">
      {/* Top nav */}
      <header className="flex items-center gap-4 px-6 py-3 border-b border-qumulo-border bg-qumulo-panel shrink-0">
        <div className="flex items-center gap-2">
          <Cpu size={20} className="text-qumulo-teal" />
          <span className="font-semibold text-white tracking-tight">Qumulo GPU Horizon</span>
          <span className="text-xs text-gray-500 ml-1">MVP</span>
        </div>

        <nav className="flex gap-1 ml-4">
          {([
            { id: 'discover' as View, icon: Map, label: 'Discover' },
            { id: 'dashboard' as View, icon: LayoutDashboard, label: 'Dashboard' },
          ] as const).map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              className={[
                'flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors',
                view === id
                  ? 'bg-qumulo-teal/20 text-qumulo-teal'
                  : 'text-gray-400 hover:text-white',
              ].join(' ')}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto text-xs text-gray-600">
          All prices are advisory · Not a binding quote
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex overflow-hidden">
        {view === 'discover' && <DiscoverPage />}
        {view === 'dashboard' && <Dashboard />}
      </main>
    </div>
  )
}
