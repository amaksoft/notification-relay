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


def grant_access(subscriber_id: str, grants_to_add: list[dict]) -> dict:
    """grants_to_add: [{package, channelIds?, deviceIds?}], one or more at
    once (see plan divergence — batch, not one-package-per-call). Each
    entry replaces any existing grant for the same package."""
    ref = _subscriber_ref(subscriber_id)
    subscriber = ref.get().to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grant_list = grants.get("grants", [])
    incoming_packages = {g["package"] for g in grants_to_add}
    grant_list = [g for g in grant_list if g.get("package") not in incoming_packages]
    for entry in grants_to_add:
        merged = {"package": entry["package"]}
        if entry.get("channelIds"):
            merged["channelIds"] = entry["channelIds"]
        if entry.get("deviceIds"):
            merged["deviceIds"] = entry["deviceIds"]
        grant_list.append(merged)
    grants["grants"] = grant_list
    ref.update({"grants": grants})
    return grants


def revoke_access(subscriber_id: str, packages: list[str]) -> dict:
    ref = _subscriber_ref(subscriber_id)
    subscriber = ref.get().to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grants["grants"] = [g for g in grants.get("grants", []) if g.get("package") not in packages]
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


def delete_subscriber(subscriber_id: str) -> int:
    """Hard delete: the subscriber doc itself, not just its webhooks — see
    disable_subscriber for the reversible, soft version. No reason to keep
    e.g. a short-lived e2e-test subscriber's record around forever."""
    ref = _subscriber_ref(subscriber_id)
    webhook_docs = list(db().collection("webhooks").where(filter=FieldFilter("subscriberId", "==", subscriber_id)).stream())
    batch = db().batch()
    for doc in webhook_docs:
        batch.delete(doc.reference)
    if webhook_docs:
        batch.commit()
    for collection_name in ("delivery_log", "test_deliveries", "access_requests", "webhook_queue"):
        log_docs = list(
            db().collection(collection_name).where(filter=FieldFilter("subscriberId", "==", subscriber_id)).stream()
        )
        batch = db().batch()
        for doc in log_docs:
            batch.delete(doc.reference)
        if log_docs:
            batch.commit()
    ref.delete()
    return len(webhook_docs)


# --- Access requests (owner review side) --------------------------------

def list_access_requests(status: str | None = "pending") -> list[dict]:
    query = db().collection("access_requests")
    if status:
        query = query.where(filter=FieldFilter("status", "==", status))
    entries = []
    for doc in query.stream():
        entry = doc.to_dict() or {}
        entry["id"] = doc.id
        entries.append(entry)
    return entries


def _access_request_ref(request_id: str):
    ref = db().collection("access_requests").document(request_id)
    doc = ref.get()
    if not doc.exists:
        raise SystemExit(f"No access request with id {request_id!r}.")
    data = doc.to_dict() or {}
    if data.get("status") != "pending":
        raise SystemExit(f"Request {request_id!r} is already {data.get('status')!r}.")
    return ref, data


def approve_access_request(request_id: str) -> dict:
    ref, access_request = _access_request_ref(request_id)
    grants = grant_access(access_request["subscriberId"], access_request["grants"])
    ref.update({"status": "approved", "resolvedAt": firestore.SERVER_TIMESTAMP})
    return grants


def deny_access_request(request_id: str) -> None:
    ref, _ = _access_request_ref(request_id)
    ref.update({"status": "denied", "resolvedAt": firestore.SERVER_TIMESTAMP})


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
