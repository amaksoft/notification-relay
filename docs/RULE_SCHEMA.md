# Rule schema

This is the single source of truth for the Condition/Rule JSON shape used by:

- the on-device rule evaluator (Kotlin, `android/app/src/main/java/.../rules/ConditionEvaluator.kt`)
  — the privacy gate deciding what ever leaves the phone
- the server-side webhook filter evaluator (Python, `functions/condition_matcher.py`) — the routing
  gate deciding which webhook(s) receive an already-ingested notification
- the shared React tree editor (`web/src/components/ConditionEditor.tsx`) used to build/edit both

Both evaluators MUST implement identical semantics. Cross-language test fixtures live in
`functions/tests/condition_fixtures.json` and are consumed by both the Python and Kotlin test suites
so the two implementations can't silently drift apart.

## Condition (recursive)

```jsonc
{
  "type": "AND",                 // see Condition types below
  "stringValue": null,           // leaf types only
  "intValue": null,              // leaf types only (NOTIFICATION_FLAG_SET)
  "conditions": [ /* Condition */ ],  // AND / OR only
  "inverse": false               // negates this node's result, valid on ANY node (leaf or branch)
}
```

### Condition types

| type | evaluates | match rule |
|---|---|---|
| `ALWAYS` | trivially true | always matches (before `inverse`) |
| `AND` | `conditions` | true iff `conditions` is non-empty AND all children true |
| `OR` | `conditions` | true iff `conditions` is non-empty AND any child true |
| `NOTIFICATION_TITLE` | notification title | `stringValue` is a case-insensitive substring of the title |
| `NOTIFICATION_TEXT` | notification text | `stringValue` is a case-insensitive substring of the text |
| `NOTIFICATION_PACKAGE_NAME` | notification package | exact string equality with `stringValue` |
| `NOTIFICATION_FLAG_SET` | notification flags (int bitmask) | `(flags & intValue) != 0` |
| `NOTIFICATION_CHANNEL_ID` | notification channel id | exact string equality with `stringValue` — **added in this project, not present in the reference app**. Since channel ids are only unique within a package's namespace, pair this with a `NOTIFICATION_PACKAGE_NAME` condition (via `AND`) in practice; nothing technically enforces that pairing since it's just another leaf in the tree. |

`inverse: true` negates whatever the node would otherwise evaluate to — apply it *after* computing
the node's own result (i.e. `NOT(AND(...))`/`NOT(OR(...))` are valid and behave as De Morgan would
suggest only if you nest explicitly; `inverse` does not push down into children automatically).

**Empty `conditions` list is `false` for both `AND` and `OR`** — this looks like an asymmetric
implementation detail rather than a deliberate design choice (a conventional reading would make empty
`AND` vacuously `true`), but it's what the decompiled bytecode actually does (both branches fall
through to the same "no match" tail), and this project mirrors it exactly for parity. In practice an
empty-children AND/OR shouldn't occur from any of the rule builders (CLI, adb, web UI) — this is a
documented edge case, not a feature anyone should rely on.

### Reference-app parity note

The first six condition types plus the recursive-tree/`inverse`-on-any-node design were reverse
engineered directly from `net.tative.notificationsrelay`'s decompiled `Condition`/`RuleEntity`
classes (title/text: case-insensitive substring; package: exact match; flags: bitmask AND). Only
`NOTIFICATION_CHANNEL_ID` is new here.

## Rule

Wraps a `Condition` with metadata. Used both for on-device rules (`devices/{id}.rules`) and
per-webhook filters (`webhooks/{id}.filter`):

```jsonc
{
  "name": "Slack mentions",
  "condition": { /* Condition */ },
  "throttleSeconds": 30,   // global per-rule cooldown: once matched, this rule won't fire again
                           // until throttleSeconds have elapsed, regardless of which notification
                           // triggers it next (keyed by rule id, not by notification content)
  "enabled": true,
  "order": 0,              // display/evaluation order only — ALL enabled rules are evaluated per
                           // notification, this is not first-match-wins
  "format": "DEFAULT"      // DEFAULT | QUICK — device-rule-only; controls the on-device payload
                           // shape sent to `ingestNotification`. Webhook filters omit this field
                           // entirely since the ingest payload is already fixed JSON by the time
                           // webhook matching runs.
}
```

## Notification record (what gets matched against)

```jsonc
{
  "package": "com.slack",
  "appName": "Slack",
  "title": "Alice mentioned you",
  "text": "Hey, can you review this PR?",
  "timestamp": 1735689600000,
  "group": false,
  "flags": 0,
  "importance": 3,
  "channelId": "slack_dm_channel",
  "channelName": "Direct messages",
  "key": "0|com.slack|...",
  "propertiesJson": "{}"     // raw extras blob, carried through but not currently used in matching
}
```

## Example

```jsonc
{
  "name": "Slack DM mentions",
  "condition": {
    "type": "AND",
    "conditions": [
      { "type": "NOTIFICATION_PACKAGE_NAME", "stringValue": "com.slack" },
      { "type": "NOTIFICATION_CHANNEL_ID", "stringValue": "slack_dm_channel" },
      { "type": "NOTIFICATION_TEXT", "stringValue": "mentioned you" }
    ]
  },
  "throttleSeconds": 30,
  "enabled": true,
  "order": 0,
  "format": "DEFAULT"
}
```

## Grant scope (subscribers) — a separate, simpler shape

Not part of the Condition tree. A subscriber's `grants` restrict which `(package, channelId)`
combinations their webhooks can ever see, enforced as a runtime pre-filter *before* their own
Condition is evaluated (see main plan for rationale — this is deliberately not structural validation
of the submitted Condition tree):

```jsonc
{
  "grants": [
    { "package": "com.slack" },                                   // whole package, any channel
    { "package": "com.whatsapp", "channelIds": ["calls_channel"] } // one specific channel only
  ]
  // OR: { "allowAll": true }
}
```
