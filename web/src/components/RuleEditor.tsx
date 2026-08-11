import ConditionEditor from './ConditionEditor'
import type { Rule } from '../types'

type Props = {
  rule: Rule
  onChange: (next: Rule) => void
  onRemove?: () => void
}

export default function RuleEditor({ rule, onChange, onRemove }: Props) {
  return (
    <div className="card rule-card">
      <div className="rule-card-header">
        <input
          type="text"
          className="rule-name-input"
          placeholder="Rule name"
          value={rule.name}
          onChange={(e) => onChange({ ...rule, name: e.target.value })}
        />
        <label className="inline-checkbox">
          <input
            type="checkbox"
            checked={rule.enabled}
            onChange={(e) => onChange({ ...rule, enabled: e.target.checked })}
          />
          Enabled
        </label>
        <label className="inline-field">
          Throttle (s)
          <input
            type="number"
            min={0}
            style={{ width: '5rem' }}
            value={rule.throttleSeconds}
            onChange={(e) => onChange({ ...rule, throttleSeconds: Number(e.target.value) })}
          />
        </label>
        {onRemove && (
          <button type="button" className="btn-danger-text" onClick={onRemove}>
            Delete rule
          </button>
        )}
      </div>
      <ConditionEditor condition={rule.condition} onChange={(condition) => onChange({ ...rule, condition })} />
    </div>
  )
}
