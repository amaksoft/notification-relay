import { useEffect, useState } from 'react'
import { listAllWebhooks, listSubscribers } from '../api'
import type { Subscriber, Webhook } from '../types'

function formatTtl(seconds?: number): string {
  if (!seconds) return '1h (default)'
  if (seconds % 3600 === 0) return `${seconds / 3600}h`
  if (seconds % 60 === 0) return `${seconds / 60}m`
  return `${seconds}s`
}

export default function Webhooks() {
  const [webhooks, setWebhooks] = useState<Webhook[] | null>(null)
  const [subscribers, setSubscribers] = useState<Record<string, Subscriber>>({})

  useEffect(() => {
    listAllWebhooks({}).then((res) => setWebhooks(res.webhooks))
    listSubscribers({}).then((res) => {
      const map: Record<string, Subscriber> = {}
      for (const s of res.subscribers) map[s.id] = s
      setSubscribers(map)
    })
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1>Webhooks</h1>
      </div>
      <p className="muted small">
        Read-only. Webhooks are created and managed by subscribers themselves via the API — this view is for oversight.
      </p>

      {webhooks === null && <p className="muted">Loading…</p>}
      {webhooks?.length === 0 && <p className="empty-state">No webhooks registered yet.</p>}

      {webhooks && webhooks.length > 0 && (
        <div className="card table-scroll">
          <table>
            <thead>
              <tr>
                <th>Subscriber</th>
                <th>URL</th>
                <th>Filter</th>
                <th>Enabled</th>
                <th>Queue TTL</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {webhooks.map((w) => (
                <tr key={w.id}>
                  <td>{subscribers[w.subscriberId]?.name ?? <code>{w.subscriberId}</code>}</td>
                  <td style={{ maxWidth: '20rem', wordBreak: 'break-all' }}>{w.url}</td>
                  <td>{w.filter.name ?? <span className="muted">{w.filter.condition.type}</span>}</td>
                  <td>
                    <span className={`badge ${w.filter.enabled ? 'badge-success' : 'badge-muted'}`}>
                      {w.filter.enabled ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td className="small muted">{formatTtl(w.queueTtlSeconds)}</td>
                  <td>{w.createdAt ? new Date(w.createdAt).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
