import { useState } from 'react'
import { GoogleAuthProvider, signInWithPopup, type AuthError } from 'firebase/auth'
import { auth } from './firebase'

const googleProvider = new GoogleAuthProvider()

export default function LoginForm() {
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSignIn() {
    setError(null)
    setSubmitting(true)
    try {
      await signInWithPopup(auth, googleProvider)
    } catch (err) {
      const code = (err as AuthError).code
      if (code !== 'auth/popup-closed-by-user' && code !== 'auth/cancelled-popup-request') {
        setError('Google sign-in failed. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="centered-page">
      <div className="card centered-card">
        <h1>Notification Relay</h1>
        <p className="muted" style={{ marginTop: '-0.5rem' }}>Admin console — owner sign-in only.</p>
        {error && <p className="notice notice-error">{error}</p>}
        <button className="btn-primary" onClick={handleSignIn} disabled={submitting} style={{ width: '100%' }}>
          {submitting ? 'Signing in…' : 'Sign in with Google'}
        </button>
      </div>
    </div>
  )
}
