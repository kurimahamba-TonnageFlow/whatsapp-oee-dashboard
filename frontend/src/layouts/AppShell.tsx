import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { ApiStatus } from '../components/ApiStatus'

const NAV_ITEMS = [
  { to: '/hmi', label: 'HMI' },
  { to: '/engineering', label: 'Engineering' },
  { to: '/management', label: 'Management' },
  { to: '/management/performance', label: 'Performance' },
  { to: '/dashboard', label: 'Dashboard' },
]

interface AppShellProps {
  children: ReactNode
}

/** Minimal application shell suitable for factory tablets, phones and
 * desktop browsers - a header, primary nav and content area, all
 * built from the shared design tokens. Not the final HMI design. */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <p className="app-shell__title">TonnageFlow Pulse</p>
        <ApiStatus />
      </header>

      <nav className="app-shell__nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              isActive
                ? 'app-shell__nav-link app-shell__nav-link--active'
                : 'app-shell__nav-link'
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <main className="app-shell__main">{children}</main>
    </div>
  )
}
