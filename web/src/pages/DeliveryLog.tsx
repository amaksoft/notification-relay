import { useEffect, useState } from 'react'
import { listDeliveryLog } from '../api'
import type { DeliveryLogEntry } from '../types'

// Channel/device ids only make sense within a package's namespace (see
// docs/RULE_SCHEMA.md) — show them qualified rather than as bare ids.
function sourceLabel(summary: DeliveryLogEntry['notificationSummary']): string {
  const pkg = summary.package ?? '—'
  const parts = [pkg]
  if (summary.channelId) parts.push(`:${summary.channelId}`)
  if (summary.deviceId) parts.push(`@${summary.deviceId}`)
  return parts.join('')
}

export default function DeliveryLog() {
  const [entries, setEntries] = useState<DeliveryLogEntry[] | null>(null)

  useEffect(() => {
    listDeliveryLog({ limit: 100 }).then((res) => setEntries(res.entries))
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1>Delivery log</h1>
      </div>
      <p className="muted small">Most recent 100 webhook deliveries, across all subscribers.</p>

      {entries === null && <p className="muted">Loading…</p>}
      {entries?.length === 0 && <p className="empty-state">No deliveries yet.</p>}

      {entries && entries.length > 0 && (
        <div className="card table-scroll">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Status</th>
                <th>Source</th>
                <th>Title</th>
                <th>Matched rule</th>
                <th>HTTP</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td>{e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}</td>
                  <td>
                    <span className={`badge ${e.status === 'delivered' ? 'badge-success' : 'badge-danger'}`}>
                      {e.status}
                    </span>
                  </td>
                  <td>
                    <code>{sourceLabel(e.notificationSummary)}</code>
                  </td>
                  <td>{e.notificationSummary.title ?? '—'}</td>
                  <td>{e.matchedRule ?? <span className="muted">—</span>}</td>
                  <td>
                    {e.httpCode ?? '—'}
                    {e.error && <div className="small muted">{e.error}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
