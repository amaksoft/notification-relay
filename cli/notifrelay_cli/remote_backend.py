"""
Firestore ("remote") backend — mirrors the same business logic as the
owner-gated Cloud Functions callables (devices_callables.py,
subscribers_callables.py) but via direct Admin SDK access instead of
calling those deployed functions. See firestore_client.py for why that's
the right shape for a CLI tool.
"""

import uuid
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from .crypto import generate_api_key, hash_api_key
from .firestore_client import db


# --- Device rules -----------------------------------------------------

def list_installed_apps(device_id: str) -> list[dict]:
    doc = db().collection("devices").document(device_id).get()
    return (doc.to_dict() or {}).get("installedApps", []) if doc.exists else []


def list_seen_channels(device_id: str, package: str | None = None) -> list[dict]:
    doc = db().collection("devices").document(device_id).get()
    channels = (doc.to_dict() or {}).get("seenChannels", []) if doc.exists else []
    if package:
        channels = [c for c in channels if c.get("package") == package]
    return channels


def list_rules(device_id: str) -> list[dict]:
    doc = db().collection("devices").document(device_id).get()
    return (doc.to_dict() or {}).get("rules", []) if doc.exists else []


def _write_rules(device_id: str, rules: list[dict]) -> None:
    db().collection("devices").document(device_id).set(
        {"rules": rules, "lastSeen": firestore.SERVER_TIMESTAMP}, merge=True
    )


def add_rule(device_id: str, rule: dict) -> str:
    rule_id = uuid.uuid4().hex[:12]
    rule = {"id": rule_id, "enabled": True, "throttleSeconds": 0, "order": 0, "format": "DEFAULT", **rule}
    rules = list_rules(device_id)
    rules.append(rule)
    _write_rules(device_id, rules)
    return rule_id


def set_rule_enabled(device_id: str, rule_id: str, enabled: bool) -> None:
    rules = list_rules(device_id)
    for rule in rules:
        if rule.get("id") == rule_id:
            rule["enabled"] = enabled
            _write_rules(device_id, rules)
            return
    raise SystemExit(f"No rule with id {rule_id!r} on device {device_id!r}.")


def remove_rule(device_id: str, rule_id: str) -> None:
    rules = list_rules(device_id)
    remaining = [r for r in rules if r.get("id") != rule_id]
    if len(remaining) == len(rules):
        raise SystemExit(f"No rule with id {rule_id!r} on device {device_id!r}.")
    _write_rules(device_id, remaining)


# --- Subscribers / grants ----------------------------------------------

def create_subscriber(name: str, grants: dict, ttl_seconds: int | None = None) -> tuple[str, str]:
    raw_key = generate_api_key()
    expires_at = None
    if ttl_seconds:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    doc_ref = db().collection("subscribers").document()
    doc_ref.set(
        {
            "name": name,
            "apiKeyHash": hash_api_key(raw_key),
            "grants": grants,
            "enabled": True,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "expiresAt": expires_at,
        }
    )
    return doc_ref.id, raw_key


def _subscriber_ref(subscriber_id: str):
    ref = db().collection("subscribers").document(subscriber_id)
    if not ref.get().exists:
        raise SystemExit(f"No subscriber with id {subscriber_id!r}.")
    return ref


def grant_access(subscriber_id: str, package: str, channel_ids: list[str] | None = None) -> dict:
    ref = _subscriber_ref(subscriber_id)
    subscriber = ref.get().to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grant_list = [g for g in grants.get("grants", []) if g.get("package") != package]
    new_grant = {"package": package}
    if channel_ids:
        new_grant["channelIds"] = channel_ids
    grant_list.append(new_grant)
    grants["grants"] = grant_list
    ref.update({"grants": grants})
    return grants


def revoke_access(subscriber_id: str, package: str) -> dict:
    ref = _subscriber_ref(subscriber_id)
    subscriber = ref.get().to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grants["grants"] = [g for g in grants.get("grants", []) if g.get("package") != package]
    ref.update({"grants": grants})
    return grants


def list_subscribers() -> list[dict]:
    subscribers = []
    for doc in db().collection("subscribers").stream():
        entry = doc.to_dict() or {}
        entry.pop("apiKeyHash", None)
        entry["id"] = doc.id
        subscribers.append(entry)
    return subscribers


def disable_subscriber(subscriber_id: str) -> int:
    ref = _subscriber_ref(subscriber_id)
    ref.update({"enabled": False})
    docs = list(db().collection("webhooks").where(filter=FieldFilter("subscriberId", "==", subscriber_id)).stream())
    batch = db().batch()
    for doc in docs:
        batch.delete(doc.reference)
    if docs:
        batch.commit()
    return len(docs)


# --- Webhooks (read-only oversight) -------------------------------------

def list_webhooks(subscriber_id: str | None = None) -> list[dict]:
    query = db().collection("webhooks")
    if subscriber_id:
        query = query.where(filter=FieldFilter("subscriberId", "==", subscriber_id))
    webhooks = []
    for doc in query.stream():
        entry = doc.to_dict() or {}
        entry["id"] = doc.id
        webhooks.append(entry)
    return webhooks
