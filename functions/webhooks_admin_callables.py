"""
Owner-only, read-only visibility across all subscribers' webhooks.
Webhooks are otherwise entirely subscriber-owned/edited via the public
API-key-gated functions in webhooks_api.py — this module never
creates/edits/deletes a webhook, only lists them for the admin UI/CLI.
"""

from firebase_functions import https_fn
from google.cloud.firestore_v1 import FieldFilter

from common import db, require_admin


@https_fn.on_call(secrets=["ALLOWED_EMAILS"], invoker="public")
def list_all_webhooks(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    subscriber_id = data.get("subscriberId")

    query = db().collection("webhooks")
    if subscriber_id:
        query = query.where(filter=FieldFilter("subscriberId", "==", subscriber_id))

    webhooks = []
    for doc in query.stream():
        entry = doc.to_dict() or {}
        entry["id"] = doc.id
        webhooks.append(entry)
    return {"webhooks": webhooks}
