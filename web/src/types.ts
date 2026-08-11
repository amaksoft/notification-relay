// Mirrors docs/RULE_SCHEMA.md - the single source of truth shared with
// the Kotlin (android/) and Python (functions/) evaluators.

export type ConditionType =
  | 'ALWAYS'
  | 'AND'
  | 'OR'
  | 'NOTIFICATION_TITLE'
  | 'NOTIFICATION_TEXT'
  | 'NOTIFICATION_PACKAGE_NAME'
  | 'NOTIFICATION_FLAG_SET'
  | 'NOTIFICATION_CHANNEL_ID'
  | 'NOTIFICATION_DEVICE_ID'

export type Condition = {
  type: ConditionType
  stringValue?: string | null
  intValue?: number | null
  conditions?: Condition[]
  inverse?: boolean
}

export type RuleFormat = 'DEFAULT' | 'QUICK'

export type Rule = {
  id?: string
  name: string
  condition: Condition
  throttleSeconds: number
  enabled: boolean
  order: number
  format?: RuleFormat
}

export type WebhookFilter = {
  name?: string
  condition: Condition
  throttleSeconds?: number
  enabled: boolean
}

export type Grant = { package: string; channelIds?: string[]; deviceIds?: string[] }
export type Grants = { grants?: Grant[]; allowAll?: boolean }

export type Subscriber = {
  id: string
  name: string
  grants: Grants
  enabled: boolean
  createdAt?: string
  expiresAt?: string | null
}

export type AccessRequest = {
  id: string
  subscriberId: string
  subscriberName?: string
  grants: Grant[]
  note?: string
  status: 'pending' | 'approved' | 'denied'
  createdAt?: string
  resolvedAt?: string | null
}

export type Webhook = {
  id: string
  subscriberId: string
  url: string
  headers?: Record<string, string>
  filter: WebhookFilter
  queueTtlSeconds?: number
  createdAt?: string
  lastFiredAt?: number
}

export type SeenChannel = {
  package: string
  channelId: string
  channelName: string
  lastSeen?: number
}

export type InstalledApp = { package: string; label: string }

export type Device = {
  id: string
  label?: string
  lastSeen?: string
  installedApps?: InstalledApp[]
  seenChannels?: SeenChannel[]
  rules?: Rule[]
}

export type DeliveryLogEntry = {
  id: string
  webhookId: string
  subscriberId: string
  notificationSummary: { package?: string; channelId?: string; deviceId?: string; title?: string }
  matchedRule?: string | null
  status: 'delivered' | 'failed'
  httpCode?: number | null
  error?: string | null
  timestamp?: string
}

export const CONDITION_LEAF_TYPES: ConditionType[] = [
  'NOTIFICATION_PACKAGE_NAME',
  'NOTIFICATION_CHANNEL_ID',
  'NOTIFICATION_DEVICE_ID',
  'NOTIFICATION_TITLE',
  'NOTIFICATION_TEXT',
  'NOTIFICATION_FLAG_SET',
  'ALWAYS',
]

export function newLeafCondition(type: ConditionType): Condition {
  if (type === 'AND' || type === 'OR') return { type, conditions: [] }
  if (type === 'NOTIFICATION_FLAG_SET') return { type, intValue: 0 }
  if (type === 'ALWAYS') return { type }
  return { type, stringValue: '' }
}

export function newRule(): Rule {
  return {
    name: '',
    condition: { type: 'AND', conditions: [] },
    throttleSeconds: 0,
    enabled: true,
    order: 0,
    format: 'DEFAULT',
  }
}
