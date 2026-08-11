import { initializeApp } from 'firebase/app'
import { browserLocalPersistence, connectAuthEmulator, getAuth, setPersistence } from 'firebase/auth'
import { connectFunctionsEmulator, getFunctions } from 'firebase/functions'

// Public client config - not a secret, ships in every built bundle
// regardless (see docs/OPERATIONS.md). Access control happens entirely
// server-side: every callable checks the caller's email against the
// ALLOWED_EMAILS Secret Manager value via require_admin().
const firebaseConfig = {
  apiKey: 'AIzaSyBoojhp-hM-i3NvrAVT2xlEjEh5qOhT8_g',
  authDomain: 'notification-relay-73586.firebaseapp.com',
  projectId: 'notification-relay-73586',
  storageBucket: 'notification-relay-73586.firebasestorage.app',
  messagingSenderId: '574093998225',
  appId: '1:574093998225:web:d92a4f2c334af99034e730',
}

export const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
export const functions = getFunctions(app, 'us-central1')

void setPersistence(auth, browserLocalPersistence)

if (import.meta.env.DEV) {
  connectAuthEmulator(auth, 'http://127.0.0.1:9099', { disableWarnings: true })
  connectFunctionsEmulator(functions, '127.0.0.1', 5001)
}
