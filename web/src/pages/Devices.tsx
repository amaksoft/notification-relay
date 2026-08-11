import { useEffect, useState } from 'react'
import type { FirebaseError } from 'firebase/app'
import { listDevices, updateDeviceRules } from '../api'
import { newRule, type Device, type Rule } from '../types'
import RuleEditor from '../components/RuleEditor'

export default function Devices() {
  const [devices, setDevices] = useState<Device[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  useEffect(() => {
    listDevices({}).then((res) => {
      setDevices(res.devices)
      if (res.devices.length > 0) setSelectedId(res.devices[0].id)
    })
  }, [])

  const selected = devices?.find((d) => d.id === selectedId) ?? null

  useEffect(() => {
    setRules(selected?.rules ?? [])
    setSavedAt(null)
  }, [selected?.id])

  async function save() {
    if (!selectedId) return
    setSaving(true)
    setError(null)
    try {
      await updateDeviceRules({ deviceId: selectedId, rules })
      setSavedAt(Date.now())
      setDevices((prev) => prev?.map((d) => (d.id === selectedId ? { ...d, rules } : d)) ?? prev)
    } catch (err) {
      setError((err as FirebaseError).message)
    } finally {
      setSaving(false)
    }
  }

  function updateRule(index: number, next: Rule) {
    setRules((prev) => prev.map((r, i) => (i === index ? next : r)))
  }

  function removeRule(index: number) {
    setRules((prev) => prev.filter((_, i) => i !== index))
  }

  function addRule() {
    setRules((prev) => [...prev, { ...newRule(), order: prev.length }])
  }

  if (devices === null) return <p className="muted">Loading devices…</p>

  if (devices.length === 0) {
    return (
      <div className="empty-state">
        <p>No devices yet.</p>
        <p className="small">Sign in with the Android app on a device to have it show up here.</p>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Devices</h1>
      </div>

      <div className="card" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {devices.map((d) => (
          <button
            key={d.id}
            onClick={() => setSelectedId(d.id)}
            style={
              d.id === selectedId
                ? { background: 'var(--accent)', borderColor: 'var(--accent)', color: 'var(--accent-contrast)' }
                : undefined
            }
          >
            {d.label || d.id}
          </button>
        ))}
      </div>

      {selected && (
        <>
          <div className="card small muted">
            <div>Device id: <code>{selected.id}</code></div>
            {selected.lastSeen && <div>Last seen: {String(selected.lastSeen)}</div>}
            <div>{selected.installedApps?.length ?? 0} installed apps reported, {selected.seenChannels?.length ?? 0} channels seen</div>
          </div>

          <div className="page-header">
            <h2>Rules</h2>
            <div className="btn-row">
              <button onClick={addRule}>+ Add rule</button>
              <button className="btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </div>

          {error && <p className="notice notice-error">{error}</p>}
          {savedAt && <p className="notice notice-success">Saved.</p>}

          {rules.length === 0 && <p className="muted">No rules yet — this device won't forward anything.</p>}

          {rules.map((rule, i) => (
            <RuleEditor key={i} rule={rule} onChange={(next) => updateRule(i, next)} onRemove={() => removeRule(i)} />
          ))}
        </>
      )}
    </div>
  )
}
