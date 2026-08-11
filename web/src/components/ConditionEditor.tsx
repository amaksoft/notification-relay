import { CONDITION_LEAF_TYPES, newLeafCondition, type Condition, type ConditionType } from '../types'

const TYPE_LABELS: Record<ConditionType, string> = {
  ALWAYS: 'Always',
  AND: 'All of (AND)',
  OR: 'Any of (OR)',
  NOTIFICATION_TITLE: 'Title contains',
  NOTIFICATION_TEXT: 'Text contains',
  NOTIFICATION_PACKAGE_NAME: 'Package is',
  NOTIFICATION_FLAG_SET: 'Flags include (bitmask)',
  NOTIFICATION_CHANNEL_ID: 'Channel ID is',
  NOTIFICATION_DEVICE_ID: 'Device ID is',
}

function isGroup(type: ConditionType): boolean {
  return type === 'AND' || type === 'OR'
}

/** Channel/device ids are only meaningful within a package's namespace
 * (see docs/RULE_SCHEMA.md) — find a sibling NOTIFICATION_PACKAGE_NAME
 * leaf in the same group so channel/device leaves can show `pkg:value`
 * instead of a bare, ambiguous id. */
function siblingPackage(siblings: Condition[] | undefined, self: Condition): string | null {
  if (!siblings) return null
  const pkg = siblings.find((c) => c !== self && c.type === 'NOTIFICATION_PACKAGE_NAME')
  return pkg?.stringValue || null
}

type Props = {
  condition: Condition
  onChange: (next: Condition) => void
  onRemove?: () => void
  depth?: number
  siblings?: Condition[]
}

export default function ConditionEditor({ condition, onChange, onRemove, depth = 0, siblings }: Props) {
  const group = isGroup(condition.type)
  const children = condition.conditions ?? []
  const siblingPkg = siblingPackage(siblings, condition)

  function setType(type: ConditionType) {
    if (isGroup(type)) {
      onChange({ type, conditions: children, inverse: condition.inverse })
    } else {
      onChange({ ...newLeafCondition(type), inverse: condition.inverse })
    }
  }

  function updateChild(index: number, next: Condition) {
    const nextChildren = children.slice()
    nextChildren[index] = next
    onChange({ ...condition, conditions: nextChildren })
  }

  function removeChild(index: number) {
    onChange({ ...condition, conditions: children.filter((_, i) => i !== index) })
  }

  function addChild(type: ConditionType) {
    onChange({ ...condition, conditions: [...children, newLeafCondition(type)] })
  }

  return (
    <div className="condition-node" style={{ marginLeft: depth > 0 ? '1.25rem' : 0 }}>
      <div className="condition-row">
        <select value={condition.type} onChange={(e) => setType(e.target.value as ConditionType)}>
          <optgroup label="Groups">
            <option value="AND">{TYPE_LABELS.AND}</option>
            <option value="OR">{TYPE_LABELS.OR}</option>
          </optgroup>
          <optgroup label="Conditions">
            {CONDITION_LEAF_TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t]}
              </option>
            ))}
          </optgroup>
        </select>

        <label className="inline-checkbox">
          <input
            type="checkbox"
            checked={condition.inverse ?? false}
            onChange={(e) => onChange({ ...condition, inverse: e.target.checked })}
          />
          NOT
        </label>

        {!group && condition.type !== 'ALWAYS' && condition.type !== 'NOTIFICATION_FLAG_SET' && (
          <>
            {(condition.type === 'NOTIFICATION_CHANNEL_ID' || condition.type === 'NOTIFICATION_DEVICE_ID') &&
              siblingPkg && <code className="small muted">{siblingPkg}:</code>}
            <input
              type="text"
              placeholder={
                condition.type === 'NOTIFICATION_CHANNEL_ID' || condition.type === 'NOTIFICATION_DEVICE_ID'
                  ? 'id'
                  : 'value'
              }
              value={condition.stringValue ?? ''}
              onChange={(e) => onChange({ ...condition, stringValue: e.target.value })}
            />
          </>
        )}

        {condition.type === 'NOTIFICATION_FLAG_SET' && (
          <input
            type="number"
            placeholder="bitmask"
            value={condition.intValue ?? 0}
            onChange={(e) => onChange({ ...condition, intValue: Number(e.target.value) })}
          />
        )}

        {onRemove && (
          <button type="button" className="btn-danger-text" onClick={onRemove}>
            Remove
          </button>
        )}
      </div>

      {group && (
        <div className="condition-children">
          {children.length === 0 && <p className="muted small">No conditions yet — this group won't match anything.</p>}
          {children.map((child, i) => (
            <ConditionEditor
              key={i}
              condition={child}
              onChange={(next) => updateChild(i, next)}
              onRemove={() => removeChild(i)}
              depth={depth + 1}
              siblings={children}
            />
          ))}
          <div className="condition-add-row" style={{ marginLeft: '1.25rem' }}>
            <select
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) {
                  addChild(e.target.value as ConditionType)
                  e.target.value = ''
                }
              }}
            >
              <option value="" disabled>
                + Add condition…
              </option>
              <optgroup label="Groups">
                <option value="AND">{TYPE_LABELS.AND}</option>
                <option value="OR">{TYPE_LABELS.OR}</option>
              </optgroup>
              <optgroup label="Conditions">
                {CONDITION_LEAF_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABELS[t]}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
        </div>
      )}
    </div>
  )
}
