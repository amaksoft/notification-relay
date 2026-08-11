import { useEffect, useState } from 'react'
import {
  approveAccessRequest,
  createSubscriber,
  deleteSubscriber,
  denyAccessRequest,
  disableSubscriber,
  grantSubscriberAccess,
  listAccessRequests,
  listSubscribers,
  revokeSubscriberAccess,
} from '../api'
import type { AccessRequest, Grant, Subscriber } from '../types'

function splitList(value: string): string[] | undefined {
  const items = value
    .split(',')
    .map((c) => c.trim())
    .filter(Boolean)
  return items.length > 0 ? items : undefined
}

function grantLabel(g: Grant): string {
  // channels/devices are only meaningful within a package's namespace
  // (see docs/RULE_SCHEMA.md) — always show them qualified as
  // package:channel / package:device rather than bare ids.
  const parts: string[] = []
  if (g.channelIds) parts.push(...g.channelIds.map((c) => `${g.package}:${c}`))
  if (g.deviceIds) parts.push(...g.deviceIds.map((d) => `${g.package}@${d}`))
  if (parts.length === 0) return `${g.package} (whole package, any device)`
  return parts.join(', ')
}

type GrantRow = { package: string; channels: string; devices: string }
const emptyRow = (): GrantRow => ({ package: '', channels: '', devices: '' })

function rowsToGrants(rows: GrantRow[]): Grant[] {
  return rows
    .filter((r) => r.package.trim())
    .map((r) => ({
      package: r.package.trim(),
      channelIds: splitList(r.channels),
      deviceIds: splitList(r.devices),
    }))
}

/** Shared by CreateSubscriberForm's initial grants and the per-subscriber
 * "add more grants" form — lets several (package, channels, devices)
 * entries be authored and submitted together in one batch call, instead
 * of one package per round-trip. */
function GrantRowsEditor({ rows, setRows }: { rows: GrantRow[]; setRows: (rows: GrantRow[]) => void }) {
  function updateRow(i: number, patch: Partial<GrantRow>) {
    setRows(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }
  function removeRow(i: number) {
    setRows(rows.filter((_, idx) => idx !== i))
  }
  return (
    <div>
      {rows.map((row, i) => (
        <div key={i} className="field-inline" style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', marginBottom: '0.5rem' }}>
          <div style={{ flex: 1 }}>
            {i === 0 && <label>Package</label>}
            <input value={row.package} onChange={(e) => updateRow(i, { package: e.target.value })} placeholder="com.slack" />
          </div>
          <div style={{ flex: 1 }}>
            {i === 0 && <label>Channel IDs (comma-separated, optional)</label>}
            <input value={row.channels} onChange={(e) => updateRow(i, { channels: e.target.value })} placeholder="dm_channel, mentions" />
          </div>
          <div style={{ flex: 1 }}>
            {i === 0 && <label>Device IDs (comma-separated, optional)</label>}
            <input value={row.devices} onChange={(e) => updateRow(i, { devices: e.target.value })} placeholder="pixel-8" />
          </div>
          {rows.length > 1 && (
            <button type="button" className="btn-danger-text" onClick={() => removeRow(i)}>
              Remove
            </button>
          )}
        </div>
      ))}
      <button type="button" onClick={() => setRows([...rows, emptyRow()])}>
        + Add another package
      </button>
    </div>
  )
}

function GrantForm({ subscriberId, onGranted }: { subscriberId: string; onGranted: (grants: Subscriber['grants']) => void }) {
  const [rows, setRows] = useState<GrantRow[]>([emptyRow()])
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const grants = rowsToGrants(rows)
    if (grants.length === 0) return
    setBusy(true)
    try {
      const res = await grantSubscriberAccess({ subscriberId, grants })
      onGranted(res.grants)
      setRows([emptyRow()])
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <GrantRowsEditor rows={rows} setRows={setRows} />
      <button type="submit" className="btn-primary" disabled={busy} style={{ marginTop: '0.5rem' }}>
        {busy ? 'Granting…' : 'Grant'}
      </button>
    </form>
  )
}

function PendingRequests({ onResolved }: { onResolved: () => void }) {
  const [requests, setRequests] = useState<AccessRequest[] | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  function refresh() {
    return listAccessRequests({ status: 'pending' }).then((res) => setRequests(res.requests))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function approve(id: string) {
    setBusyId(id)
    try {
      await approveAccessRequest({ requestId: id })
      await refresh()
      onResolved()
    } finally {
      setBusyId(null)
    }
  }

  async function deny(id: string) {
    setBusyId(id)
    try {
      await denyAccessRequest({ requestId: id })
      await refresh()
    } finally {
      setBusyId(null)
    }
  }

  if (requests === null || requests.length === 0) return null

  return (
    <div className="card">
      <h2>Pending access requests</h2>
      {requests.map((r) => (
        <div key={r.id} style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem', marginTop: '0.75rem' }}>
          <div className="page-header">
            <div>
              <strong>{r.subscriberName ?? r.subscriberId}</strong> requests:
              <div className="small" style={{ marginTop: '0.25rem' }}>
                {r.grants.map((g, i) => (
                  <span key={i} className="badge badge-muted" style={{ marginRight: '0.35rem' }}>
                    {grantLabel(g)}
                  </span>
                ))}
              </div>
              {r.note && <p className="small muted" style={{ marginTop: '0.35rem' }}>"{r.note}"</p>}
            </div>
            <div className="btn-row">
              <button className="btn-primary" disabled={busyId === r.id} onClick={() => approve(r.id)}>
                Approve
              </button>
              <button className="btn-danger-text" disabled={busyId === r.id} onClick={() => deny(r.id)}>
                Deny
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Subscribers() {
  const [subscribers, setSubscribers] = useState<Subscriber[] | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newApiKey, setNewApiKey] = useState<{ name: string; key: string } | null>(null)

  function refresh() {
    return listSubscribers({}).then((res) => setSubscribers(res.subscribers))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleDisable(id: string) {
    if (!confirm('Disable this subscriber? Their webhooks will be deleted. The subscriber record itself is kept — use Delete to remove it entirely.')) return
    await disableSubscriber({ subscriberId: id })
    refresh()
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Permanently delete "${name}"? This removes the subscriber, its webhooks, and all its logs/requests. This cannot be undone.`)) return
    await deleteSubscriber({ subscriberId: id })
    refresh()
  }

  async function handleRevoke(id: string, pkg: string) {
    await revokeSubscriberAccess({ subscriberId: id, packages: [pkg] })
    refresh()
  }

  return (
    <div>
      <div className="page-header">
        <h1>Subscribers</h1>
        <button className="btn-primary" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? 'Cancel' : '+ New subscriber'}
        </button>
      </div>

      <PendingRequests onResolved={refresh} />

      {showCreate && (
        <CreateSubscriberForm
          onCreated={(name, key) => {
            setNewApiKey({ name, key })
            setShowCreate(false)
            refresh()
          }}
        />
      )}

      {newApiKey && (
        <div className="card notice notice-success" style={{ marginTop: 0 }}>
          <strong>{newApiKey.name}</strong> created. API key (shown once — copy it now):
          <div style={{ marginTop: '0.5rem' }}>
            <code style={{ wordBreak: 'break-all' }}>{newApiKey.key}</code>
          </div>
          <button style={{ marginTop: '0.5rem' }} onClick={() => setNewApiKey(null)}>
            Dismiss
          </button>
        </div>
      )}

      {subscribers === null && <p className="muted">Loading…</p>}
      {subscribers?.length === 0 && <p className="empty-state">No subscribers yet.</p>}

      {subscribers?.map((s) => (
        <div key={s.id} className="card">
          <div className="page-header">
            <div>
              <h2 style={{ marginBottom: '0.15rem' }}>{s.name}</h2>
              <span className={`badge ${s.enabled ? 'badge-success' : 'badge-muted'}`}>
                {s.enabled ? 'Enabled' : 'Disabled'}
              </span>{' '}
              <span className="badge badge-muted">
                {s.expiresAt ? `Expires ${new Date(s.expiresAt).toLocaleString()}` : 'No expiry'}
              </span>
            </div>
            <div className="btn-row">
              {s.enabled && (
                <button className="btn-danger-text" onClick={() => handleDisable(s.id)}>
                  Disable
                </button>
              )}
              <button className="btn-danger-text" onClick={() => handleDelete(s.id, s.name)}>
                Delete
              </button>
            </div>
          </div>
          <p className="small muted">
            Id: <code>{s.id}</code>
          </p>

          <h3 style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>Grants</h3>
          {s.grants.allowAll ? (
            <p className="badge badge-success">All packages / channels / devices</p>
          ) : (s.grants.grants?.length ?? 0) === 0 ? (
            <p className="muted small">No grants yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Package</th>
                  <th>Scope</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {s.grants.grants!.map((g) => (
                  <tr key={g.package}>
                    <td>
                      <code>{g.package}</code>
                    </td>
                    <td>{grantLabel(g)}</td>
                    <td>
                      {s.enabled && (
                        <button className="btn-danger-text" onClick={() => handleRevoke(s.id, g.package)}>
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {s.enabled && !s.grants.allowAll && (
            <div style={{ marginTop: '0.75rem' }}>
              <GrantForm
                subscriberId={s.id}
                onGranted={(grants) =>
                  setSubscribers((prev) => prev?.map((x) => (x.id === s.id ? { ...x, grants } : x)) ?? prev)
                }
              />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function CreateSubscriberForm({ onCreated }: { onCreated: (name: string, key: string) => void }) {
  const [name, setName] = useState('')
  const [allowAll, setAllowAll] = useState(false)
  const [rows, setRows] = useState<GrantRow[]>([emptyRow()])
  const [ttl, setTtl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const grants = allowAll ? { allowAll: true } : { grants: rowsToGrants(rows) }
      const ttlSeconds = ttl.trim() ? Number(ttl) : undefined
      const res = await createSubscriber({ name: name.trim(), grants, ttlSeconds })
      onCreated(name.trim(), res.apiKey)
    } catch {
      setError('Failed to create subscriber.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="card">
      <div className="field">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="field">
        <label className="inline-checkbox">
          <input type="checkbox" checked={allowAll} onChange={(e) => setAllowAll(e.target.checked)} />
          Allow all packages/channels/devices
        </label>
      </div>
      {!allowAll && (
        <div className="field">
          <label>Initial grants (optional — can add more later)</label>
          <GrantRowsEditor rows={rows} setRows={setRows} />
        </div>
      )}
      <div className="field">
        <label>TTL in seconds (optional — leave blank for no expiry)</label>
        <input value={ttl} onChange={(e) => setTtl(e.target.value)} placeholder="3600" type="number" min={0} />
      </div>
      {error && <p className="notice notice-error">{error}</p>}
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy ? 'Creating…' : 'Create subscriber'}
      </button>
    </form>
  )
}
