import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { signOut } from 'firebase/auth'
import { auth } from './firebase'
import { useAuthUser } from './useAuthUser'
import { listDevices } from './api'
import LoginForm from './LoginForm'
import Layout from './Layout'
import Devices from './pages/Devices'
import Subscribers from './pages/Subscribers'
import Webhooks from './pages/Webhooks'
import DeliveryLog from './pages/DeliveryLog'

type AuthzState = 'checking' | 'authorized' | 'denied'

export default function App() {
  const { user, loading } = useAuthUser()
  const [authz, setAuthz] = useState<AuthzState>('checking')

  useEffect(() => {
    if (!user) {
      setAuthz('checking')
      return
    }
    // Authorization is enforced entirely server-side (ALLOWED_EMAILS,
    // see require_admin) — there is no client-visible allowlist to check
    // against, so a cheap read-only call doubles as the authorization
    // probe for the whole app.
    let cancelled = false
    listDevices({})
      .then(() => !cancelled && setAuthz('authorized'))
      .catch((err: unknown) => {
        if (cancelled) return
        const code = (err as { code?: string }).code
        setAuthz(code === 'functions/permission-denied' ? 'denied' : 'authorized')
      })
    return () => {
      cancelled = true
    }
  }, [user])

  if (loading) return null

  if (!user) return <LoginForm />

  if (authz === 'checking') return null

  if (authz === 'denied') {
    return (
      <div className="centered-page">
        <div className="card centered-card">
          <h1>Not authorized</h1>
          <p className="muted">Signed in as {user.email}, but this account isn't allowed to manage this project.</p>
          <button style={{ width: '100%' }} onClick={() => signOut(auth)}>
            Sign out
          </button>
        </div>
      </div>
    )
  }

  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/devices" replace />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/subscribers" element={<Subscribers />} />
          <Route path="/webhooks" element={<Webhooks />} />
          <Route path="/delivery-log" element={<DeliveryLog />} />
          <Route path="*" element={<Navigate to="/devices" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
