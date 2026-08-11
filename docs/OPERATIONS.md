# Operations

## One-time project setup

1. `firebase use --add` (or edit `.firebaserc` directly) to point this repo at the actual Firebase
   project ID, once created.
2. `firebase functions:secrets:set ALLOWED_EMAILS` → enter `amaksoft@gmail.com` (comma-separate if
   more owner emails are ever added). Never hardcode this anywhere in source.
3. Enable in the Firebase console (or via `firebase` CLI): Authentication → Google sign-in provider,
   Firestore, Functions, Hosting.

## Gitignored assets that must exist before things work

Per the [[feedback_gitignored_deploy_assets]] lesson (a past outage): every file below is
intentionally gitignored, but that means it must be **regenerated on any fresh checkout/deploy
machine** — never assume it's already there.

- `cli/notifrelay_cli/service-account.json` — Firebase Admin SDK service-account key used by the CLI
  for its Firestore ("remote") backend. Generate via Firebase console → Project Settings → Service
  Accounts → "Generate new private key", or `gcloud iam service-accounts keys create`. Without this
  file, every `notifrelay` command that isn't purely local/adb will fail at startup with a clear
  "credentials not found" error (fail loud, not silently).
- `android/app/google-services.json` — Firebase Android app config (API key, project id, OAuth
  client id for Google Sign-In). Regenerate with `android/scripts/fetch_google_services.sh` (needs
  `firebase login`). Gitignored by user preference, not because the key is a real secret — it's
  Firebase's public client key, baked into every built APK either way; Firestore/Auth security comes
  from security rules and the ALLOWED_EMAILS allowlist, not from this file staying hidden.

## Deploying

- Functions + Firestore rules: `firebase deploy --only functions,firestore`
- Hosting (after `cd web && npm run build`): `firebase deploy --only hosting`
- Everything: `firebase deploy`

## Local development

- `firebase emulators:start` — auth (9099), functions (5001), firestore (8080), hosting (5000), UI.
- Point the CLI at the emulator with `--emulator` (uses `FIRESTORE_EMULATOR_HOST` under the hood)
  instead of real Firestore/Admin credentials.

## Logging and alerting

Every Cloud Function logs via the standard `logging` module. `common.py` sets the root logger level
to `INFO` at import time — Python's root logger defaults to `WARNING`, which was silently dropping
every `logging.info(...)` call in this codebase (confirmed missing entirely from Cloud Logging, not
just filtered client-side) until this was added. If you add a new function file, `import common`
before logging anything, or the level fix won't have run yet.

- `ingest_notification`: logs an `ERROR` when a webhook exhausts both delivery attempts, and wraps
  each webhook's processing in its own try/except so one malformed webhook (e.g. a bad `filter`
  shape) can't abort delivery to every other webhook in the same fan-out — logged via
  `logging.exception` (full traceback) rather than crashing the whole call.
- `purge_expired_subscribers`: logs an `INFO` summary every run (`purged N expired subscriber(s)`),
  including when N=0 — this is the only way to tell "ran and found nothing" apart from "silently
  stopped running" from Cloud Logging alone.
- `webhooks_api`'s test-delivery endpoint logs a `WARNING` on failure (previously only returned to
  the caller, invisible to us as operators).

**Alerting**: a Cloud Monitoring alert policy (`notification-relay: function errors`, project
`notification-relay-73586`) fires on any `severity>=ERROR` log entry from `resource.type=
"cloud_run_revision"` (i.e. any of these Cloud Functions) and emails amaksoft@gmail.com, rate-limited
to once per 30 minutes so a burst of the same error doesn't spam. Manage it via:

```
gcloud monitoring policies list --project notification-relay-73586
gcloud monitoring policies describe <policy-name> --project notification-relay-73586
```

(`gcloud` lives at `~/google-cloud-sdk/bin` on this Pi, not on `PATH` by default — the `alpha`/`beta`
components were installed once to manage notification channels/policies.)

This alerting setup itself caught a real bug during setup: `purge_expired_subscribers` had been
returning HTTP 500 on **every single hourly run** since it was first deployed, because its
`(enabled, expiresAt)` Firestore query needed a composite index that was never created — silently
means it never purged anything, ever, until `firestore.indexes.json` was fixed and deployed. Watch
for `firestore` `FAILED_PRECONDITION`/"requires an index" errors in Cloud Logging after adding any
new multi-field `.where()` query; deploy the fix with `firebase deploy --only firestore:indexes` and
give it a minute or two to finish building (`gcloud firestore indexes composite list`) before
retrying.

## Webhook delivery: push, then poll-queue fallback

Real-time push (`ingest.py`'s `_deliver`) is the fast path: 2 attempts, 5s timeout each, no backoff,
retried only on network-level failure (not on a bad HTTP response like a 503 — that's treated as "we
got a response" and not retried). Total window is ~10 seconds, not longer — **this is not a "we'll
keep trying for a while" retry**, it's a short best-effort attempt.

If push fails (network error, timeout, or non-2xx), the notification is queued to `webhook_queue`
instead of being dropped, with an `expiresAt` = now + the webhook's `queueTtlSeconds` (subscriber-set
at webhook create/update time, default 1h via `DEFAULT_QUEUE_TTL_SECONDS`, capped at 24h via
`MAX_QUEUE_TTL_SECONDS`). A subscriber that was briefly down can then poll:

```
GET /api/webhooks/{id}/queue
Authorization: Bearer <api-key>
```

This is **pop semantics** — whatever's returned is deleted immediately as part of the same call
(at-most-once; if the subscriber's HTTP client dies mid-response, those items are gone). Queueing
only happens on push failure, never on push success, so a healthy subscriber gets exactly one
delivery (via push) and never needs to poll at all.

`expiresAt` must stay a real Firestore `Timestamp` (not a raw number) — that's a hard requirement for
Firestore's native per-collection TTL policy to pick the field up. That native sweep is storage
cleanup only (items never polled by anyone) and can lag up to ~24h; the poll query's own `expiresAt >
now` filter is the actual correctness boundary, always enforced regardless of sweep timing. One-time
setup (already done for this project, re-run if `webhook_queue` is ever recreated):

```
gcloud firestore fields ttls update expiresAt --collection-group=webhook_queue \
  --enable-ttl --project=notification-relay-73586
```

## End-to-end verification

Two layers, covering different parts of the pipe:

### Automated backend e2e — `python3 e2e/run_e2e.py`

Exercises everything server-side (grant gate, Condition matching including
`NOTIFICATION_DEVICE_ID`, batch grants, the access-request approve/deny flow, hard-delete cascades,
and the push→poll-queue TTL fallback) by calling `ingest_notification` directly with a real
owner-signed ID token — minted via `firebase_admin.auth.create_custom_token` + the Identity Toolkit
REST API's `signInWithCustomToken`, exactly the same callable the phone itself calls, just without a
physical device in the loop. Self-cleaning (each scenario registers its own teardown in a
`finally`), safe to run repeatedly, exits non-zero on any failure. Requires
`cli/notifrelay_cli/service-account.json` (same Admin SDK key the CLI uses).

```
python3 e2e/run_e2e.py
```

Add a new scenario function + append it to `SCENARIOS` when adding a new backend capability — this
is meant to grow with the project, not stay a one-off script.

### Manual device-side e2e — testapp + `test_receiver`

The one thing the automated script above deliberately does NOT cover: whether a real Android
`NotificationListenerService` actually captures a notification and builds the same payload
`ingest_notification` expects. That still needs a physical device (see plan's "End-to-end
verification harness" section):

```
notifrelay device rule add --package com.amaksoft.notifrelay.testapp --channel test_channel_a
notifrelay subscriber create --name e2e-test \
  --grant com.amaksoft.notifrelay.testapp:test_channel_a --ttl 1h
# register a webhook with the printed key, pointing at /api/test-receiver
notifrelay test post-notification --channel test_channel_a --title "e2e" --text "hello"
# check test_deliveries in Firestore/emulator UI for the matching row
notifrelay subscriber delete <id>   # hard delete; explicit cleanup — prefer this over `disable`
                                     # for throwaway/test subscribers, see "Deleting subscribers"
                                     # below. --ttl above is the crash-safety fallback either way.
notifrelay device rule remove <rule-id>
```

## Grants: package, channel, and device scoping

A grant entry is `package[:channelIds][@deviceIds]` — channels and devices are independent,
optional dimensions (omit either for "no restriction on that dimension"). Multiple grants can be
issued in one call/command (batch, not one round-trip per package):

```
notifrelay subscriber create --name my-sub \
  --grant com.slack \
  --grant "com.whatsapp:calls_channel" \
  --grant "com.whatsapp:messages_channel@pixel-8,pixel-9"

notifrelay subscriber grant <id> --grant "com.slack:dm_channel@pixel-8"
notifrelay subscriber revoke <id> --package com.slack --package com.whatsapp
```

Device scoping is deliberately both: the owner grants which device(s) a subscriber may see
(`deviceIds` on the grant — enforced server-side, same pre-filter-then-Condition ordering as
package/channel), and once granted, a subscriber can further self-filter by device in their own
webhook's Condition tree via `NOTIFICATION_DEVICE_ID` — see docs/RULE_SCHEMA.md.

## Deleting subscribers: disable vs. delete

- `notifrelay subscriber disable <id>` — soft: sets `enabled: false`, cascades-deletes the
  subscriber's webhooks, but **keeps the subscriber doc itself** (name, grants, hashed key) — use
  this if you might want to re-enable them later. `purge_expired_subscribers` does NOT touch
  disabled subscribers (it only queries `enabled == true`), so a disabled subscriber's record
  lingers forever unless explicitly deleted.
- `notifrelay subscriber delete <id>` — hard: removes the subscriber doc, its webhooks, and all its
  `delivery_log`/`test_deliveries`/`access_requests` rows. No reason to keep e.g. an e2e-test
  subscriber's record around forever just because it once existed. **Prefer this for throwaway/test
  subscribers.**
- Any subscriber created with `--ttl` gets hard-deleted automatically once `expiresAt` passes, via
  the same `purge_expired_subscribers` scheduled function (runs hourly) — this is the crash-safety
  fallback for e2e runs, not a substitute for explicit cleanup in the happy path.

## Self-service access requests

API keys stay owner-issued only (unchanged) — but a subscriber holding one can request additional
grants themselves instead of the owner running a CLI command based on some out-of-band ask:

```
# subscriber side (their own script, using their API key):
curl -X POST https://notification-relay-73586.web.app/api/access-requests \
  -H "Authorization: Bearer <their-api-key>" -H "Content-Type: application/json" \
  -d '{"grants": [{"package": "com.slack", "channelIds": ["dm_channel"]}], "note": "for X"}'

# owner side:
notifrelay subscriber requests list                 # defaults to --status pending
notifrelay subscriber requests approve <request-id>  # merges into the subscriber's grants
notifrelay subscriber requests deny <request-id>
```

Same review queue is in the admin web UI under Subscribers → "Pending access requests". A
subscriber is capped at 10 pending requests at once (`MAX_PENDING_REQUESTS_PER_SUBSCRIBER` in
`access_requests_api.py`) to bound Firestore writes from a misbehaving script.
