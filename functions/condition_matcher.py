"""
Shared Condition/Rule evaluator — see docs/RULE_SCHEMA.md, the single
source of truth for this schema. Must stay in sync with the Kotlin
ConditionEvaluator; cross-language fixtures live in
functions/tests/condition_fixtures.json and are consumed by both test
suites.

Deliberately pure (no Firestore/network I/O) so it's trivially unit
testable and mirrors the Kotlin side one-to-one. Throttle-state
persistence lives in ingest.py, which has access to Firestore — this
module only exposes the pure decision function.
"""

from __future__ import annotations

from typing import Any

Notification = dict[str, Any]
Condition = dict[str, Any]
Grants = dict[str, Any]


def _contains(haystack: str | None, needle: str | None) -> bool:
    return (needle or "").lower() in (haystack or "").lower()


def evaluate_condition(condition: Condition, notification: Notification) -> bool:
    """Evaluate a single Condition node against a notification record.

    Reverse-engineered from net.tative.notificationsrelay's decompiled
    Condition/matcher classes: title/text use case-insensitive substring
    matching, package/channel use exact string equality, flags use bitmask
    AND. An empty `conditions` list on AND/OR evaluates to False for both
    (see docs/RULE_SCHEMA.md) — a quirk of the reference app's actual
    bytecode, preserved here for parity rather than "fixed" to the more
    conventional vacuous-true-for-AND reading.
    """
    node_type = condition.get("type")
    children = condition.get("conditions") or []

    if node_type == "ALWAYS":
        result = True
    elif node_type == "AND":
        result = bool(children) and all(evaluate_condition(c, notification) for c in children)
    elif node_type == "OR":
        result = bool(children) and any(evaluate_condition(c, notification) for c in children)
    elif node_type == "NOTIFICATION_TITLE":
        result = _contains(notification.get("title"), condition.get("stringValue"))
    elif node_type == "NOTIFICATION_TEXT":
        result = _contains(notification.get("text"), condition.get("stringValue"))
    elif node_type == "NOTIFICATION_PACKAGE_NAME":
        result = notification.get("package") == condition.get("stringValue")
    elif node_type == "NOTIFICATION_CHANNEL_ID":
        result = notification.get("channelId") == condition.get("stringValue")
    elif node_type == "NOTIFICATION_DEVICE_ID":
        result = notification.get("deviceId") == condition.get("stringValue")
    elif node_type == "NOTIFICATION_FLAG_SET":
        flags = int(notification.get("flags") or 0)
        mask = int(condition.get("intValue") or 0)
        result = (flags & mask) != 0
    else:
        raise ValueError(f"Unknown condition type: {node_type!r}")

    return (not result) if condition.get("inverse") else result


def rule_matches(rule: dict, notification: Notification) -> bool:
    """Whether a Rule (device rule or webhook filter) matches — enabled
    check plus the Condition tree. Does NOT apply throttling; the caller
    (which owns the persisted last-fired state) does that separately via
    throttle_allows below."""
    if not rule.get("enabled", True):
        return False
    return evaluate_condition(rule["condition"], notification)


def throttle_allows(last_fired_at: float | None, throttle_seconds: int, now: float) -> bool:
    """Pure per-rule cooldown check (rule matched -> should it actually
    fire, given when it last fired?). Mirrors the reference app's
    global-per-rule-id throttle semantics: a rule that already fired
    within throttleSeconds is skipped regardless of which notification
    triggers it. The caller is responsible for reading/writing
    last_fired_at (Firestore on the server side, Room on-device) —
    this function only makes the yes/no decision."""
    if throttle_seconds <= 0:
        return True
    if last_fired_at is None:
        return True
    return (now - last_fired_at) >= throttle_seconds


def is_in_grant(package: str, channel_id: str | None, device_id: str | None, grants: Grants | None) -> bool:
    """The runtime pre-filter gate for subscriber scope (see plan
    Architecture overview / RULE_SCHEMA.md Grant scope): checked BEFORE
    the subscriber's own webhook Condition ever runs, so no Condition tree
    -- however adversarial with OR/NOT -- can ever match outside the
    grant. `grants` is the subscriber doc's grant shape:
    {"allowAll": true} or
    {"grants": [{"package": ..., "channelIds": [...]?, "deviceIds": [...]?}]}.
    Omitting channelIds/deviceIds on a grant entry means "no restriction on
    that dimension" (whole package, any channel/device) — each dimension is
    independently AND'd when present.
    """
    if not grants:
        return False
    if grants.get("allowAll"):
        return True
    for grant in grants.get("grants", []):
        if grant.get("package") != package:
            continue
        channel_ids = grant.get("channelIds")
        if channel_ids and channel_id not in channel_ids:
            continue
        device_ids = grant.get("deviceIds")
        if device_ids and device_id not in device_ids:
            continue
        return True
    return False
