"""
Owner-gated device management: rule CRUD (the on-device privacy-filter
rule set, edited from the web UI or the CLI's Firestore backend) and
device status reporting (installed apps / seen channels, pushed by the
phone itself so the CLI/web UI have a picker to build rules against).
"""

from firebase_admin import firestore
from firebase_functions import https_fn
from firebase_functions.https_fn import FunctionsErrorCode, HttpsError

from common import db, require_admin

ALLOWED_EMAILS_SECRET = ["ALLOWED_EMAILS"]


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def update_device_rules(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    device_id = data.get("deviceId")
    rules = data.get("rules")
    if not device_id or rules is None:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "deviceId and rules are required.")
    db().collection("devices").document(device_id).set(
        {"rules": rules, "lastSeen": firestore.SERVER_TIMESTAMP}, merge=True
    )
    return {"ok": True}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def list_device_rules(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    device_id = data.get("deviceId")
    if not device_id:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "deviceId is required.")
    doc = db().collection("devices").document(device_id).get()
    if not doc.exists:
        return {"rules": []}
    return {"rules": (doc.to_dict() or {}).get("rules", [])}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def list_devices(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    devices = []
    for doc in db().collection("devices").stream():
        entry = doc.to_dict() or {}
        entry["id"] = doc.id
        devices.append(entry)
    return {"devices": devices}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def report_device_status(request: https_fn.CallableRequest) -> dict:
    """Called by the phone itself (owner-authenticated, same Firebase Auth
    identity used for ingestNotification) to report its installed-app list
    and any newly seen notification channels. Merge-set so repeated calls
    only ever add to installedApps/seenChannels, never require the caller
    to resend the whole rule set."""
    require_admin(request)
    data = request.data or {}
    device_id = data.get("deviceId")
    if not device_id:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "deviceId is required.")

    update = {"lastSeen": firestore.SERVER_TIMESTAMP}
    if data.get("label") is not None:
        update["label"] = data["label"]
    if data.get("installedApps") is not None:
        update["installedApps"] = data["installedApps"]
    if data.get("seenChannels") is not None:
        update["seenChannels"] = data["seenChannels"]

    db().collection("devices").document(device_id).set(update, merge=True)
    return {"ok": True}
