import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { signOut } from 'firebase/auth'
import { auth } from './firebase'
import { useAuthUser } from './useAuthUser'

const NAV_ITEMS = [
  { to: '/devices', label: 'Devices' },
  { to: '/subscribers', label: 'Subscribers' },
  { to: '/webhooks', label: 'Webhooks' },
  { to: '/delivery-log', label: 'Delivery log' },
]

export default function Layout({ children }: { children: ReactNode }) {
  const { user } = useAuthUser()

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-brand">Notification Relay</span>
        <nav className="app-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'active' : '')}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="app-header-user">
          <span className="muted small">{user?.email}</span>
          <button className="link-button" onClick={() => signOut(auth)}>
            Sign out
          </button>
        </div>
      </header>
      <main className="app-body">{children}</main>
    </div>
  )
}
