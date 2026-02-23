import { NavLink, Outlet } from 'react-router-dom'
import clsx from 'clsx'

const NAV = [
  { to: '/',           label: 'Overview',   icon: '◈' },
  { to: '/documents',  label: 'Documents',  icon: '▤' },
  { to: '/runs',       label: 'Runs',       icon: '⟳' },
  { to: '/analytics',  label: 'Analytics',  icon: '∿' },
  { to: '/export',     label: 'Export',     icon: '↓' },
]

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      {/* ── Sidebar ─────────────────────────────────────────────────── */}
      <aside
        className="flex flex-col flex-shrink-0 w-52 border-r"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-base)' }}
      >
        {/* Logo */}
        <div className="px-5 py-6 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="font-display italic text-xl leading-none" style={{ color: 'var(--gold)' }}>
            EDGAR
          </div>
          <div
            className="font-mono text-[10px] tracking-[0.18em] uppercase mt-1"
            style={{ color: 'var(--text-dim)' }}
          >
            Intelligence
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-0.5">
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-md text-[13px] font-medium transition-all duration-150',
                  isActive
                    ? 'text-white'
                    : 'hover:text-white'
                )
              }
              style={({ isActive }) => ({
                background: isActive ? 'var(--bg-hover)' : 'transparent',
                color: isActive ? 'var(--text-primary)' : 'var(--text-dim)',
                borderLeft: isActive ? '2px solid var(--gold)' : '2px solid transparent',
              })}
            >
              <span className="font-mono text-base w-4 text-center" style={{ color: 'var(--gold)' }}>
                {icon}
              </span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t" style={{ borderColor: 'var(--border)' }}>
          <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>
            SEC EDGAR Pipeline
          </div>
          <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-dim)', opacity: 0.6 }}>
            v1.0.0
          </div>
        </div>
      </aside>

      {/* ── Main content ────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
