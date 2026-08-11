# Subscriber guide — integrating with notification-relay

This is a reference for building an integration against the notification-relay webhook API. It's
written to be self-contained: everything you need (base URL, auth, endpoints, payload shapes,
examples) is here, no source access required.

**Production base URL: `https://notification-relay-73586.web.app/api`**

If you're an LLM/coding agent building an integration from this doc: every request/response shape
below is copy-paste accurate to the deployed API as of this writing — use the curl examples as
ground truth for request shape, and the JSON schemas for response shape.

## What this service does

The owner runs an Android app that watches their phone's notifications and forwards a subset of them
(picked by rules they control) to this backend. The backend then fans each forwarded notification out
to registered webhooks — but **only within whatever scope the owner has granted your subscriber
identity**. You never see anything outside your grant, no matter how you write your own filter.

You (a subscriber) don't touch the phone or the owner's rules at all. Your job is:
1. Get an API key from the owner (out-of-band — there is no self-service signup).
2. Register one or more webhooks, each with your own filter Condition, within your granted scope.
3. Receive POSTs at your webhook URL when something matches.

## Authentication

Every request needs your API key as a bearer token:

```
Authorization: Bearer <your-api-key>
```

There is no self-service key issuance — the owner runs a CLI command to create your subscriber
identity and hands you the key once, out-of-band. It is never retrievable again after that; if you
lose it, ask the owner to disable your old subscriber and issue a new one. Keys are hashed at rest,
never logged, never returned by any endpoint.

All endpoints respond `401 {"error": "Invalid or missing API key."}` if the key is missing, wrong, or
belongs to a disabled subscriber.

All responses are JSON, `Content-Type: application/json`, CORS-enabled (`Access-Control-Allow-Origin:
*`) — safe to call directly from a browser-based integration, not just server-to-server.

## Grants: what you're actually allowed to see

Before your own webhook filter ever runs, every notification is checked against your subscriber's
**grant** — set by the owner, not by you. A grant restricts which `(package, channelId, deviceId)`
combinations you can ever receive, regardless of what your own filter says:

```jsonc
{
  "grants": [
    { "package": "com.slack" },                                    // whole package, any channel/device
    { "package": "com.whatsapp", "channelIds": ["calls_channel"] }, // one channel, any device
    { "package": "com.whatsapp", "deviceIds": ["pixel-8"] }         // any channel, one device
  ]
  // or the whole thing could be: { "allowAll": true }
}
```

`package` is an Android package id (e.g. `com.slack`), `channelId` is that app's notification-channel
id (channel ids are only unique *within* a package — always think of them as `package:channelId`
pairs), `deviceId` identifies which of the owner's devices sent it. Ask the owner what you've been
granted, or request more (see "Requesting more access" below) — there's no endpoint for you to read
your own grant directly, since it's owner-controlled state, not yours to introspect via the API
(check with the owner, or watch what actually arrives).

## Webhook management

### `POST /api/webhooks` — register a webhook

```
curl -X POST https://notification-relay-73586.web.app/api/webhooks \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-server.example.com/hook",
    "headers": { "X-My-Secret": "optional-custom-header" },
    "filter": {
      "condition": { "type": "NOTIFICATION_PACKAGE_NAME", "stringValue": "com.slack" },
      "enabled": true
    },
    "queueTtlSeconds": 3600
  }'
```

Body fields:

| field | required | notes |
|---|---|---|
| `url` | yes | must be `https://`; loopback/private/link-local/metadata-endpoint hosts are rejected (SSRF guard) |
| `headers` | no | extra headers merged into every delivery POST (in addition to `Content-Type: application/json`, which is always set) |
| `filter` | yes | `{ condition, enabled, name?, throttleSeconds? }` — see "Filter schema" below. This is entirely yours to author; the owner's grant is enforced separately and first (see above) |
| `queueTtlSeconds` | no | how long a failed delivery stays in the poll-queue fallback before it's gone for good. Default `3600` (1h), max `86400` (24h) — see "Delivery: push, then poll" below |

Response `201`: `{"id": "<webhook-id>"}`

You can have at most **20 webhooks** at once. Creating a 21st fails with `400 {"error": "Webhook limit (20) reached."}`.

### `GET /api/webhooks` — list your webhooks

```
curl https://notification-relay-73586.web.app/api/webhooks -H "Authorization: Bearer <api-key>"
```

Response: `{"webhooks": [{id, subscriberId, url, headers, filter, queueTtlSeconds, createdAt, lastFiredAt}, ...]}` — only ever your own.

### `PATCH /api/webhooks/{id}` — update a webhook

Same body shape as create, but every field is optional — only what you send gets changed:

```
curl -X PATCH https://notification-relay-73586.web.app/api/webhooks/<id> \
  -H "Authorization: Bearer <api-key>" -H "Content-Type: application/json" \
  -d '{"filter": {"condition": {"type": "ALWAYS"}, "enabled": false}}'
```

Response: `{"ok": true}`. `404` if the webhook doesn't exist or isn't yours.

### `DELETE /api/webhooks/{id}` — delete a webhook

```
curl -X DELETE https://notification-relay-73586.web.app/api/webhooks/<id> -H "Authorization: Bearer <api-key>"
```

Response: `{"ok": true}`. Also clears anything currently sitting in its poll queue.

### `POST /api/webhooks/{id}/test` — send yourself a synthetic test payload

Useful for verifying your endpoint is reachable and parses the payload correctly, without waiting for
a real notification:

```
curl -X POST https://notification-relay-73586.web.app/api/webhooks/<id>/test -H "Authorization: Bearer <api-key>"
```

Sends a fake notification (`package: "com.example.test"`) to your registered URL immediately,
bypassing grants/filters entirely. Response: `{"ok": true, "httpCode": 200}` or `{"ok": false, "error": "..."}`.

## What you receive

When a notification matches your grant and your filter, we `POST` this to your webhook URL:

```jsonc
{
  "notification": {
    "package": "com.slack",
    "appName": "Slack",
    "title": "Alice mentioned you",
    "text": "Hey, can you review this PR?",
    "timestamp": 1735689600000,
    "flags": 0,
    "importance": 3,
    "channelId": "slack_dm_channel",
    "channelName": "Direct messages",
    "deviceId": "a1b2c3d4-...",
    "key": "0|com.slack|..."
  },
  "matchedRule": "my filter's name, or null if you didn't set one"
}
```

(`docs/RULE_SCHEMA.md` additionally documents `group` and `propertiesJson` fields on the notification
record — as of this writing the Android app doesn't actually populate either one in the payload it
sends, so don't rely on them being present.)

We treat any `2xx` response as success. Anything else (or a connection failure/timeout) counts as a
failed delivery — see the next section for what happens then.

## Delivery: push, then poll-queue fallback

**Push is the fast path and is best-effort, not guaranteed**: up to 2 attempts, 5-second timeout
each, no delay between them — a ~10 second window total, not "we'll keep retrying for a while."
Retries only happen on network-level failure (timeout, connection refused, DNS failure) — a `5xx`/`429`
response from your server is *not* retried a second time within that window.

**If push fails, the notification is queued instead of dropped** — for `queueTtlSeconds` (default 1h,
your choice at webhook create/update time, capped at 24h). If your server was briefly down, poll to
catch up on whatever's still within that window:

```
curl https://notification-relay-73586.web.app/api/webhooks/<id>/queue -H "Authorization: Bearer <api-key>"
```

Response: `{"items": [{"notification": {...}, "matchedRule": "..."}, ...]}` — up to 50 at a time,
oldest-first.

**This is pop semantics**: whatever's returned is deleted immediately, before you even see the
response. If your process crashes mid-response, those items are gone — poll only when you're actually
ready to process the result. Queueing only ever happens after a push failure, never after a push
success, so a healthy, always-up webhook never needs to poll at all — it's purely a catch-up
mechanism for downtime, not a second delivery path you need to reconcile against push.

Items past their TTL are never returned by a poll, even if not yet physically purged from storage —
don't rely on the queue as a general-purpose durable log; it's a short-lived catch-up buffer, not an
event store.

## Filter schema

Your `filter.condition` is a recursive tree — same shape used throughout the whole system (see the
full spec in `docs/RULE_SCHEMA.md` if you need the authoritative source, this is the summary you need
for webhook filters specifically):

```jsonc
{
  "type": "AND",                  // see condition types below
  "stringValue": null,            // leaf types only
  "intValue": null,               // leaf types only (NOTIFICATION_FLAG_SET)
  "conditions": [ /* nested Condition objects, AND/OR only */ ],
  "inverse": false                // negates this node's result — valid on ANY node, leaf or group
}
```

| type | matches when |
|---|---|
| `ALWAYS` | always (before `inverse`) |
| `AND` | `conditions` is non-empty AND every child matches |
| `OR` | `conditions` is non-empty AND any child matches |
| `NOTIFICATION_TITLE` | `stringValue` is a case-insensitive substring of the notification's title |
| `NOTIFICATION_TEXT` | `stringValue` is a case-insensitive substring of the notification's text |
| `NOTIFICATION_PACKAGE_NAME` | exact match against `package` |
| `NOTIFICATION_CHANNEL_ID` | exact match against `channelId` — pair with `NOTIFICATION_PACKAGE_NAME` via `AND`, channel ids are only unique within a package |
| `NOTIFICATION_DEVICE_ID` | exact match against `deviceId` — lets you split streams per physical device (e.g. "work phone" vs "personal phone") within whatever devices your grant already covers |
| `NOTIFICATION_FLAG_SET` | `(flags & intValue) != 0` |

**Empty `conditions` on `AND`/`OR` is `false`, not vacuously `true`** — an empty group matches
nothing, don't rely on it as a no-op passthrough.

Example — Slack DM mentions only, on one specific device:

```jsonc
{
  "condition": {
    "type": "AND",
    "conditions": [
      { "type": "NOTIFICATION_PACKAGE_NAME", "stringValue": "com.slack" },
      { "type": "NOTIFICATION_CHANNEL_ID", "stringValue": "slack_dm_channel" },
      { "type": "NOTIFICATION_TEXT", "stringValue": "mentioned you" },
      { "type": "NOTIFICATION_DEVICE_ID", "stringValue": "a1b2c3d4-..." }
    ]
  },
  "enabled": true,
  "name": "Slack DM mentions (work phone)",
  "throttleSeconds": 30
}
```

`throttleSeconds` (optional, default 0): once this filter matches and fires, it won't fire again for
that many seconds, regardless of what triggers it next — a cooldown keyed to the webhook, not to
notification content.

Remember: your filter only ever runs on notifications **already inside your granted scope** — you
can write as permissive a filter as you like (even `{"type": "ALWAYS"}`), it will never surface
anything the owner hasn't granted you.

## Requesting more access

You can't grant yourself anything — only the owner can — but you can *ask*, instead of needing them
to run a CLI command based on some out-of-band message:

### `POST /api/access-requests`

```
curl -X POST https://notification-relay-73586.web.app/api/access-requests \
  -H "Authorization: Bearer <api-key>" -H "Content-Type: application/json" \
  -d '{
    "grants": [{ "package": "com.whatsapp", "channelIds": ["calls_channel"] }],
    "note": "optional — why you want this"
  }'
```

`grants` is the same shape as the Grant scope above — one or more `{package, channelIds?,
deviceIds?}` entries in one request. Response `201`: `{"id": "<request-id>"}`.

You're capped at **10 pending requests** at once (`400` if you try to exceed it — wait for the owner
to review your existing ones first).

### `GET /api/access-requests` — check your own requests' status

```
curl https://notification-relay-73586.web.app/api/access-requests -H "Authorization: Bearer <api-key>"
```

Response: `{"requests": [{id, grants, note, status: "pending"|"approved"|"denied", createdAt, resolvedAt}, ...]}`
— only ever your own requests. There's no cancel/withdraw endpoint; if you no longer want a pending
request granted, just tell the owner to deny it.

## Error format

Every error response is `{"error": "<human-readable message>"}` with a non-2xx status code (`400`
validation, `401` auth, `404` not found/not yours, `502` on a test-delivery network failure). There
is no machine-readable error code field — match on status code + message text if you need to branch
on error type.
