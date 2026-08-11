"""
Owner-gated subscriber access management. This is the CLI's/admin UI's
main job (see plan Context): issuing API keys and granting/revoking
exactly which (package, channelId) combinations a subscriber can see.
Webhooks themselves are NOT managed here — subscribers own and edit
their own webhooks via the public API-key-gated functions in
webhooks_api.py; this module only ever touches the `subscribers`
collection (plus a cascade-delete of a subscriber's webhooks on disable).
"""

import logging
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore
from firebase_functions import https_fn, scheduler_fn
from firebase_functions.https_fn import FunctionsErrorCode, HttpsError
from google.cloud.firestore_v1 import FieldFilter

from common import db, generate_api_key, hash_api_key, require_admin

ALLOWED_EMAILS_SECRET = ["ALLOWED_EMAILS"]


def _delete_subscriber_webhooks(subscriber_id: str) -> int:
    docs = list(db().collection("webhooks").where(filter=FieldFilter("subscriberId", "==", subscriber_id)).stream())
    batch = db().batch()
    for doc in docs:
        batch.delete(doc.reference)
    if docs:
        batch.commit()
    return len(docs)


def _delete_subscriber_logs(subscriber_id: str) -> None:
    for collection_name in ("delivery_log", "test_deliveries", "access_requests", "webhook_queue"):
        docs = list(
            db().collection(collection_name).where(filter=FieldFilter("subscriberId", "==", subscriber_id)).stream()
        )
        batch = db().batch()
        for doc in docs:
            batch.delete(doc.reference)
        if docs:
            batch.commit()


def _hard_delete_subscriber(subscriber_id: str) -> int:
    """Fully removes a subscriber: its webhooks, delivery/test-delivery/
    access-request logs, and the subscriber doc itself. No reason to keep
    e.g. a short-lived e2e-test subscriber's records around forever —
    used both by the owner-invoked delete_subscriber callable and by
    purge_expired_subscribers once a subscriber's TTL has passed."""
    webhooks_deleted = _delete_subscriber_webhooks(subscriber_id)
    _delete_subscriber_logs(subscriber_id)
    db().collection("subscribers").document(subscriber_id).delete()
    return webhooks_deleted


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def create_subscriber(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    name = (data.get("name") or "").strip()
    if not name:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "name is required.")

    grants = data.get("grants") or {"grants": []}
    ttl_seconds = data.get("ttlSeconds")
    expires_at = None
    if ttl_seconds:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(ttl_seconds))

    raw_key = generate_api_key()
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
    # The only time the plaintext key is ever available — the caller must
    # capture it now, there is no retrieval path afterwards.
    return {"id": doc_ref.id, "apiKey": raw_key}


def _validate_grant_entry(entry: dict) -> str | None:
    if not isinstance(entry, dict) or not entry.get("package"):
        return "each grant entry needs a package."
    return None


def merge_grants_into_subscriber(subscriber_id: str, new_grants: list[dict]) -> dict:
    """Shared by grant_subscriber_access (owner-initiated) and
    approve_access_request (subscriber-requested, owner-approved) — both
    end up doing exactly the same merge. Each entry is {package,
    channelIds?, deviceIds?}; an entry replaces any existing grant for the
    same package. Raises HttpsError NOT_FOUND if the subscriber doesn't
    exist. Returns the updated grants dict."""
    doc_ref = db().collection("subscribers").document(subscriber_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Subscriber not found.")

    subscriber = doc.to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grant_list = grants.get("grants", [])
    incoming_packages = {entry["package"] for entry in new_grants}
    grant_list = [g for g in grant_list if g.get("package") not in incoming_packages]
    for entry in new_grants:
        merged = {"package": entry["package"]}
        if entry.get("channelIds"):
            merged["channelIds"] = entry["channelIds"]
        if entry.get("deviceIds"):
            merged["deviceIds"] = entry["deviceIds"]
        grant_list.append(merged)
    grants["grants"] = grant_list
    doc_ref.update({"grants": grants})
    return grants


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def grant_subscriber_access(request: https_fn.CallableRequest) -> dict:
    """Merges one or more grant entries into a subscriber's grants in a
    single call (batch — see plan divergence: granting several apps/
    channels/devices at once shouldn't need one round-trip per package).
    Each entry is {package, channelIds?, deviceIds?}; channelIds/deviceIds
    omitted means "no restriction on that dimension" (see
    condition_matcher.is_in_grant)."""
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")
    new_grants = data.get("grants")
    if not subscriber_id or not isinstance(new_grants, list) or not new_grants:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "subscriberId and a non-empty grants array are required.")
    for entry in new_grants:
        error = _validate_grant_entry(entry)
        if error:
            raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, error)

    grants = merge_grants_into_subscriber(subscriber_id, new_grants)
    return {"grants": grants}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def revoke_subscriber_access(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")
    packages = data.get("packages")
    if not subscriber_id or not isinstance(packages, list) or not packages:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "subscriberId and a non-empty packages array are required.")

    doc_ref = db().collection("subscribers").document(subscriber_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Subscriber not found.")

    subscriber = doc.to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grant_list = [g for g in grants.get("grants", []) if g.get("package") not in packages]
    grants["grants"] = grant_list
    doc_ref.update({"grants": grants})
    return {"grants": grants}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def list_subscribers(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    subscribers = []
    for doc in db().collection("subscribers").stream():
        entry = doc.to_dict() or {}
        entry.pop("apiKeyHash", None)  # never surface even the hash to any client
        entry["id"] = doc.id
        subscribers.append(entry)
    return {"subscribers": subscribers}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def disable_subscriber(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")
    if not subscriber_id:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "subscriberId is required.")

    doc_ref = db().collection("subscribers").document(subscriber_id)
    if not doc_ref.get().exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Subscriber not found.")

    doc_ref.update({"enabled": False})
    deleted = _delete_subscriber_webhooks(subscriber_id)
    return {"ok": True, "webhooksDeleted": deleted}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def delete_subscriber(request: https_fn.CallableRequest) -> dict:
    """Hard delete — permanently removes the subscriber doc itself, not
    just its webhooks (see disable_subscriber for the reversible, soft
    version). Works regardless of current enabled state."""
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")
    if not subscriber_id:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "subscriberId is required.")

    doc_ref = db().collection("subscribers").document(subscriber_id)
    if not doc_ref.get().exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Subscriber not found.")

    webhooks_deleted = _hard_delete_subscriber(subscriber_id)
    return {"ok": True, "webhooksDeleted": webhooks_deleted}


@scheduler_fn.on_schedule(schedule="every 60 minutes", secrets=ALLOWED_EMAILS_SECRET)
def purge_expired_subscribers(event: scheduler_fn.ScheduledEvent) -> None:
    """General safety net for any short-lived subscriber (test or not,
    see plan) — not test-only machinery. Hard-deletes (not just disables)
    anything past its expiresAt: there's no reason to keep e.g. an
    e2e-test subscriber's record around forever just because it once
    existed — see _hard_delete_subscriber."""
    now = datetime.now(timezone.utc)
    expired = list(
        db()
        .collection("subscribers")
        .where(filter=FieldFilter("enabled", "==", True))
        .where(filter=FieldFilter("expiresAt", "<=", now))
        .stream()
    )
    for doc in expired:
        _hard_delete_subscriber(doc.id)

    # INFO even on a no-op run (not just when something was purged) - the
    # only way to tell "this ran and found nothing" apart from "this
    # silently stopped running" from Cloud Logging alone.
    logging.info("purge_expired_subscribers: purged %d expired subscriber(s)", len(expired))
