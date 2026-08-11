"""
Owner-gated subscriber access management. This is the CLI's/admin UI's
main job (see plan Context): issuing API keys and granting/revoking
exactly which (package, channelId) combinations a subscriber can see.
Webhooks themselves are NOT managed here — subscribers own and edit
their own webhooks via the public API-key-gated functions in
webhooks_api.py; this module only ever touches the `subscribers`
collection (plus a cascade-delete of a subscriber's webhooks on disable).
"""

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
    for collection_name in ("delivery_log", "test_deliveries"):
        docs = list(
            db().collection(collection_name).where(filter=FieldFilter("subscriberId", "==", subscriber_id)).stream()
        )
        batch = db().batch()
        for doc in docs:
            batch.delete(doc.reference)
        if docs:
            batch.commit()


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


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def grant_subscriber_access(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")
    package = data.get("package")
    channel_ids = data.get("channelIds")  # omitted/None = whole package
    if not subscriber_id or not package:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "subscriberId and package are required.")

    doc_ref = db().collection("subscribers").document(subscriber_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Subscriber not found.")

    subscriber = doc.to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grant_list = grants.get("grants", [])
    grant_list = [g for g in grant_list if g.get("package") != package]
    new_grant = {"package": package}
    if channel_ids:
        new_grant["channelIds"] = channel_ids
    grant_list.append(new_grant)
    grants["grants"] = grant_list
    doc_ref.update({"grants": grants})
    return {"grants": grants}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def revoke_subscriber_access(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")
    package = data.get("package")
    if not subscriber_id or not package:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "subscriberId and package are required.")

    doc_ref = db().collection("subscribers").document(subscriber_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Subscriber not found.")

    subscriber = doc.to_dict() or {}
    grants = subscriber.get("grants") or {"grants": []}
    grant_list = [g for g in grants.get("grants", []) if g.get("package") != package]
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


@scheduler_fn.on_schedule(schedule="every 60 minutes", secrets=ALLOWED_EMAILS_SECRET)
def purge_expired_subscribers(event: scheduler_fn.ScheduledEvent) -> None:
    """General safety net for any short-lived subscriber (test or not,
    see plan) — not test-only machinery. Disables + deletes webhooks and
    prunes logs for anything past its expiresAt."""
    now = datetime.now(timezone.utc)
    expired = (
        db()
        .collection("subscribers")
        .where(filter=FieldFilter("enabled", "==", True))
        .where(filter=FieldFilter("expiresAt", "<=", now))
        .stream()
    )
    for doc in expired:
        subscriber_id = doc.id
        doc.reference.update({"enabled": False})
        _delete_subscriber_webhooks(subscriber_id)
        _delete_subscriber_logs(subscriber_id)
