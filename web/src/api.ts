import { httpsCallable } from 'firebase/functions'
import { functions } from './firebase'
import type { AccessRequest, Device, DeliveryLogEntry, Grant, Grants, Rule, Subscriber, Webhook } from './types'

function call<Req, Res>(name: string) {
  const callable = httpsCallable<Req, Res>(functions, name)
  return async (data: Req): Promise<Res> => (await callable(data)).data
}

export const listDevices = call<Record<string, never>, { devices: Device[] }>('list_devices')
export const listDeviceRules = call<{ deviceId: string }, { rules: Rule[] }>('list_device_rules')
export const updateDeviceRules = call<{ deviceId: string; rules: Rule[] }, { ok: boolean }>('update_device_rules')

export const listSubscribers = call<Record<string, never>, { subscribers: Subscriber[] }>('list_subscribers')
export const createSubscriber = call<
  { name: string; grants: Grants; ttlSeconds?: number },
  { id: string; apiKey: string }
>('create_subscriber')
export const grantSubscriberAccess = call<{ subscriberId: string; grants: Grant[] }, { grants: Grants }>(
  'grant_subscriber_access',
)
export const revokeSubscriberAccess = call<{ subscriberId: string; packages: string[] }, { grants: Grants }>(
  'revoke_subscriber_access',
)
export const disableSubscriber = call<{ subscriberId: string }, { ok: boolean; webhooksDeleted: number }>(
  'disable_subscriber',
)
export const deleteSubscriber = call<{ subscriberId: string }, { ok: boolean; webhooksDeleted: number }>(
  'delete_subscriber',
)

export const listAllWebhooks = call<{ subscriberId?: string }, { webhooks: Webhook[] }>('list_all_webhooks')

export const listDeliveryLog = call<{ subscriberId?: string; limit?: number }, { entries: DeliveryLogEntry[] }>(
  'list_delivery_log',
)

export const listAccessRequests = call<{ status?: string }, { requests: AccessRequest[] }>('list_access_requests')
export const approveAccessRequest = call<{ requestId: string }, { ok: boolean; grants: Grants }>(
  'approve_access_request',
)
export const denyAccessRequest = call<{ requestId: string }, { ok: boolean }>('deny_access_request')
