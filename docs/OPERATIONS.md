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

## Deploying

- Functions + Firestore rules: `firebase deploy --only functions,firestore`
- Hosting (after `cd web && npm run build`): `firebase deploy --only hosting`
- Everything: `firebase deploy`

## Local development

- `firebase emulators:start` — auth (9099), functions (5001), firestore (8080), hosting (5000), UI.
- Point the CLI at the emulator with `--emulator` (uses `FIRESTORE_EMULATOR_HOST` under the hood)
  instead of real Firestore/Admin credentials.

## End-to-end verification

See the plan's "End-to-end verification harness" section for the full scripted flow (testapp +
`test_receiver` + a short-TTL subscriber). Steps, once the pieces exist:

```
notifrelay device rule add --package com.amaksoft.notifrelay.testapp --channel test_channel_a
notifrelay subscriber create --name e2e-test \
  --grant com.amaksoft.notifrelay.testapp:test_channel_a --ttl 1h
# register a webhook with the printed key, pointing at /api/test-receiver
notifrelay test post-notification --channel test_channel_a --title "e2e" --text "hello"
# check test_deliveries in Firestore/emulator UI for the matching row
notifrelay subscriber disable <id>   # explicit cleanup; --ttl above is the crash-safety fallback
notifrelay device rule remove <rule-id>
```
