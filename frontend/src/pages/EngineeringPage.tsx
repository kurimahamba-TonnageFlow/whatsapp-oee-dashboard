import { Link } from 'react-router-dom'
import { EngineeringScreen } from '../features/engineering/EngineeringScreen'
import '../features/engineering/engineering.css'

/** Deliberately does NOT render inside AppShell, unlike most other
 * pages: Engineering needs to be fast and distraction-free during a
 * breakdown, and EngineeringScreen already provides its own header
 * (engineer name, logout, refresh, connection state) and its own
 * "Back to HMI" link on the login screen - wrapping it in AppShell's
 * separate header/nav would duplicate both. */
export function EngineeringPage() {
  return <><nav aria-label="Home"><Link to="/" style={{ display: 'inline-block', padding: '12px 24px' }}>Home</Link></nav><EngineeringScreen /></>
}
