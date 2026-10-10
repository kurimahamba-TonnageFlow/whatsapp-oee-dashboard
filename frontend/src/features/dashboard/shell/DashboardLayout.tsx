import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ApiStatus } from '../../../components/ApiStatus'
import { formatSessionEnd } from '../../management/destinations'
import { useManagementSession } from '../../management/session/useManagementSession'
import { DASHBOARD_PAGES, OTHER_AREAS, type DashboardNavItem } from './navigation'
import '../ui/dashboard-theme.css'

function sideLinkClass(secondary: boolean) {
  return ({ isActive }: { isActive: boolean }) =>
    [
      'pd-nav__link',
      secondary ? 'pd-nav__link--secondary' : '',
      isActive ? 'pd-nav__link--active' : '',
    ]
      .filter(Boolean)
      .join(' ')
}

function SideLink({ item, secondary = false }: { item: DashboardNavItem; secondary?: boolean }) {
  const label = item.newTab ? `${item.label} (opens in a new tab)` : item.label
  return (
    <li>
      <NavLink
        to={item.to}
        // /dashboard is Production only - not also active on the other pages.
        end
        className={sideLinkClass(secondary)}
        // Keeps the name when the rail hides the text on tablets.
        aria-label={label}
        title={label}
        {...(item.newTab ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      >
        <span className="pd-nav__icon" aria-hidden="true">
          {item.icon}
        </span>
        <span className="pd-nav__label" aria-hidden="true">
          {item.label}
        </span>
      </NavLink>
    </li>
  )
}

/** Who is signed in, when the session ends, and Log Out - one instance,
 * visible at every screen width. */
function SessionStrip() {
  const { session, signOut } = useManagementSession()
  const navigate = useNavigate()
  if (!session) return null
  const endsAt = formatSessionEnd(session.expiresAt)

  return (
    <div className="pd-session" role="region" aria-label="Management session">
      <p>
        Signed in as <strong>{session.managerName}</strong>
        {endsAt && <span className="pd-muted"> · Session ends {endsAt}</span>}
      </p>
      <button
        type="button"
        className="pd-button"
        onClick={() => {
          signOut()
          navigate('/management', { replace: true })
        }}
      >
        Log Out
      </button>
    </div>
  )
}

/**
 * The shared dark shell for the four management dashboard pages:
 * Tonnage Flow branding, left navigation with the active page
 * highlighted, the Management session strip and API status. Rendered
 * inside ManagementSessionRoot (one session for the whole Management
 * area) and behind RequireManagementSession.
 */
export function DashboardLayout() {
  return (
    <div className="pd">
      <aside className="pd-side">
        <div className="pd-side__inner">
          <div className="pd-brand">
            <span className="pd-brand__mark" aria-hidden="true">
              ◉
            </span>
            <span className="pd-brand__text">
              TONNAGE <b>FLOW</b>
              <small>Pulse</small>
            </span>
          </div>

          <nav aria-label="Primary">
            <p className="pd-nav__heading">Dashboard</p>
            <ul className="pd-nav__group">
              {DASHBOARD_PAGES.map((item) => (
                <SideLink key={item.to} item={item} />
              ))}
            </ul>
            <p className="pd-nav__heading">Other areas</p>
            <ul className="pd-nav__group pd-nav__group--secondary">
              {OTHER_AREAS.map((item) => (
                <SideLink key={item.to} item={item} secondary />
              ))}
            </ul>
          </nav>

          <div className="pd-side__foot">
            <ApiStatus />
            <span>Tonnage Flow Pulse · Management</span>
          </div>
        </div>
      </aside>

      <div className="pd-main">
        <div className="pd-topbar">
          {/* Phones only: the side rail is hidden, so the four pages become tabs. */}
          <nav className="pd-topnav" aria-label="Dashboard pages">
            <ul className="pd-topnav__links">
              {DASHBOARD_PAGES.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <NavLink to="/" className="pd-button">Home</NavLink>
          <SessionStrip />
        </div>
        <main className="pd-page">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
