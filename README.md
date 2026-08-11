# notification-relay

A personal Android notification-forwarding system: an Android app privacy-filters your phone's
notifications on-device, a Firebase backend routes matches to external subscribers' webhooks (only
within scope the owner explicitly grants), and subscribers author their own delivery filters.

**Production:**
- Admin console: `https://notification-relay-73586.web.app` (Google Sign-In, owner-only)
- API base URL: `https://notification-relay-73586.web.app/api`

## Documentation

| Doc | Audience | Covers |
|---|---|---|
| [`docs/SUBSCRIBER_GUIDE.md`](docs/SUBSCRIBER_GUIDE.md) | Third parties integrating with the webhook API | Auth, webhook CRUD, filter schema, delivery payload, push/poll-queue fallback, access requests |
| [`docs/ADMIN_GUIDE.md`](docs/ADMIN_GUIDE.md) | The owner, operating day-to-day | Web console + CLI: devices/rules, subscribers, grants, access-request review, troubleshooting |
| [`docs/RULE_SCHEMA.md`](docs/RULE_SCHEMA.md) | Implementers | The Condition/Rule JSON schema shared by the Android app, backend, and web UI — single source of truth |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Deploying/maintaining this project | Setup, deploying, logging/alerting, Firestore indexes, e2e verification |

## Repo layout

```
android/      Kotlin app (main app + testapp e2e-harness module)
functions/    Python 3.13 Cloud Functions (Firestore, all business logic)
web/          React + Vite + TS admin console
cli/          Python CLI (notifrelay) — adb/local and Firestore/remote backends
e2e/          Automated end-to-end test script (python3 e2e/run_e2e.py)
docs/         See table above
```
