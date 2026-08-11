# Admin guide — operating notification-relay

This is a reference for day-to-day operation of notification-relay as the owner: managing devices,
device rules, subscribers, grants, and access requests via the web console and CLI. For deploying,
Firestore indexes, logging/alerting, and other engineering-ops concerns, see `docs/OPERATIONS.md`
instead — this doc is about *using* the system, not standing it up.

**Production admin console: `https://notification-relay-73586.web.app`** — Google Sign-In, restricted
to the owner account (`amaksoft@gmail.com`, enforced server-side via a Secret Manager allowlist, not
hardcoded in any client). Anyone else who signs in sees "Not authorized."

If you're an LLM/coding agent operating this on the owner's behalf: this doc plus
`docs/SUBSCRIBER_GUIDE.md` (what to hand a new subscriber) together cover the whole surface — CLI
commands here are copy-paste accurate to what's deployed.

## The two management surfaces

- **Web console** (`https://notification-relay-73586.web.app`) — Devices (rule tree editor),
  Subscribers (create/grant/revoke/disable/delete, one-time API key reveal, pending access-request
  review), Webhooks (read-only cross-subscriber oversight), Delivery log.
- **CLI** (`notifrelay`, run from `cli/` as `python3 -m notifrelay_cli.cli ...`) — same capabilities,
  scriptable. Talks to Firestore directly via a service-account key (`cli/notifrelay_cli/service-account.json`,
  gitignored — see `docs/OPERATIONS.md` "Gitignored assets" if it's missing) for subscriber/grant/
  webhook-oversight commands, and either adb (`--local`, default when exactly one device is
  connected) or Firestore (`--remote`) for device rules.

Both talk to the same Firestore state — use whichever's convenient, they're interchangeable.

## Devices & rules

A "device" is one phone running the Android app — each gets a `devices/{deviceId}` Firestore doc,
auto-created on first sign-in, holding its installed-app list, seen notification channels, and its
own rule set (the on-device privacy filter: nothing leaves the phone unless a rule matches).

```
notifrelay device list-apps                          # installed-app picker data
notifrelay device list-channels [--package X]         # seen-channel picker data (only channels the
                                                        # phone has actually observed at least once)
notifrelay device rule list
notifrelay device rule add --name X --package com.slack [--channel Y] \
  [--title-contains STR] [--text-contains STR] [--throttle N]
notifrelay device rule add-json --file rule.json       # power path: full AND/OR/NOT Condition tree
notifrelay device rule enable/disable/remove <rule-id>
```

`--local`/`--remote` on any of these overrides auto-detection; `notifrelay device use <device-id>`
sets a default so you don't have to pass `--device-id` every time. Full Condition/Rule schema
(shared with webhook filters) is in `docs/RULE_SCHEMA.md`; the web console's Devices page has a
full visual AND/OR/NOT tree editor if you don't want to hand-write JSON.

## Subscribers & grants

A subscriber is a third party (or their app) you've decided to let receive some slice of your
notifications. See `docs/SUBSCRIBER_GUIDE.md` for what *they* do with the key once they have it —
this section is entirely the owner side.

### Creating a subscriber

```
notifrelay subscriber create --name "some integration" \
  --grant com.slack \
  --grant "com.whatsapp:calls_channel" \
  --grant "com.whatsapp:messages_channel@pixel-8,pixel-9" \
  --ttl 1h
```

Prints the subscriber id and the **plaintext API key, shown exactly once** — copy it now, there's no
retrieval path afterward (only a hash is stored). Hand it to the subscriber out-of-band; there is no
self-service key issuance.

`--grant` is repeatable, one package per flag, format `package[:channel1,channel2][@device1,device2]`
— channels and devices are independent optional dimensions (omit either for "no restriction on that
dimension"). `--allow-all` grants everything instead. `--ttl` (e.g. `30m`, `1h`, `2d`) is optional —
omit for no expiry; if set, the subscriber (and everything referencing it) is **automatically
hard-deleted** once it passes, via an hourly scheduled sweep — see "Deleting subscribers" below.

### Adjusting grants later

```
notifrelay subscriber grant <id> --grant "com.slack:dm_channel@pixel-8" --grant com.gmail
notifrelay subscriber revoke <id> --package com.slack --package com.whatsapp
```

Both are batch operations — multiple packages in one call, not one round-trip each. A `grant` call
for a package that's already granted replaces that package's existing grant entry (not additive
merge of channel/device lists within the same call — pass the full set you want for that package).

### Reviewing self-service access requests

A subscriber holding a key can *request* additional grants themselves (`POST /api/access-requests` —
see subscriber guide) instead of you needing to run a command based on some out-of-band ask. Review
them:

```
notifrelay subscriber requests list                   # defaults to --status pending
notifrelay subscriber requests approve <request-id>    # merges into the subscriber's grants
notifrelay subscriber requests deny <request-id>
```

Same queue appears in the web console under Subscribers → "Pending access requests," with
Approve/Deny buttons. A subscriber is capped at 10 pending requests at once.

### Disabling vs. deleting

```
notifrelay subscriber disable <id>   # soft: cascades-deletes their webhooks, keeps the record
notifrelay subscriber delete <id>    # hard: removes the subscriber, webhooks, and ALL its logs/
                                      # requests. Cannot be undone.
```

Disable if you might re-enable later; delete for anything throwaway (test subscribers, one-off
integrations you're done with). Disabled subscribers are **not** touched by the automatic TTL sweep
(it only ever acts on `enabled: true` subscribers past their `expiresAt`) — a disabled subscriber's
record lingers forever unless you explicitly delete it.

### Listing

```
notifrelay subscriber list
```

Shows every subscriber (enabled or not) with their grants and expiry — never the API key itself,
only its existence is implied.

## Webhooks (read-only oversight)

Webhooks are entirely subscriber-owned — they create/edit/delete their own via the API (see
subscriber guide). You get read-only visibility:

```
notifrelay webhook list [--subscriber-id <id>]
```

Same table (subscriber, URL, filter, enabled, queue TTL, created) is on the web console's Webhooks
page.

## Delivery log

Web console only (`Delivery log` page) — most recent 100 deliveries across all subscribers: status
(delivered/failed), source (`package:channel@device`), matched rule, HTTP code, and error text for
failures. Useful for "did notification X actually reach subscriber Y" troubleshooting. A `failed`
entry means the real-time push attempt exhausted its retries and the notification was queued for the
subscriber to poll instead (or wasn't, if `queueTtlSeconds` ran out) — see the subscriber guide's
"Delivery: push, then poll-queue fallback" section for the exact retry/TTL semantics.

## Troubleshooting checklist

- **Subscriber says they're not receiving anything**: check `notifrelay subscriber list` for their
  grants — most "not working" reports are a grant that doesn't cover the `(package, channelId,
  deviceId)` they expect. Check the Delivery log for `failed` entries with an error message.
- **A subscriber's webhook is failing repeatedly**: they get at most a ~10s real-time retry window
  (2 attempts) before falling back to their own poll queue — tell them to check `GET
  .../webhooks/{id}/queue` if their server was down.
- **An hourly scheduled job stopped doing anything**: `purge_expired_subscribers` runs every 60
  minutes — see `docs/OPERATIONS.md`'s "Logging and alerting" section for how a missing Firestore
  index once caused this to silently fail on every run, and how the alert policy now catches this
  class of bug going forward.
