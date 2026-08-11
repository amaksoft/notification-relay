"""
Owner-only review side of the self-service access-request flow (see
access_requests_api.py for the subscriber-facing submission endpoint).
The owner is still the sole authority over what a subscriber can
actually see — approving a request is the only path that ever touches
`subscribers/{id}.grants`.
"""

from firebase_admin import firestore
from firebase_functions import https_fn
from firebase_functions.https_fn import FunctionsErrorCode, HttpsError
from google.cloud.firestore_v1 import FieldFilter

from common import db, require_admin
from subscribers_callables import ALLOWED_EMAILS_SECRET, merge_grants_into_subscriber


def _get_pending_request(request_id: str):
    doc_ref = db().collection("access_requests").document(request_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HttpsError(FunctionsErrorCode.NOT_FOUND, "Access request not found.")
    data = doc.to_dict() or {}
    if data.get("status") != "pending":
        raise HttpsError(FunctionsErrorCode.FAILED_PRECONDITION, f"Request already {data.get('status')}.")
    return doc_ref, data


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def list_access_requests(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    status = data.get("status", "pending")  # default to pending — that's the actionable queue

    query = db().collection("access_requests")
    if status:
        query = query.where(filter=FieldFilter("status", "==", status))

    entries = []
    for doc in query.stream():
        entry = doc.to_dict() or {}
        entry["id"] = doc.id
        entries.append(entry)
    return {"requests": entries}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def approve_access_request(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    request_id = data.get("requestId")
    if not request_id:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "requestId is required.")

    doc_ref, access_request = _get_pending_request(request_id)
    grants = merge_grants_into_subscriber(access_request["subscriberId"], access_request["grants"])
    doc_ref.update({"status": "approved", "resolvedAt": firestore.SERVER_TIMESTAMP})
    return {"ok": True, "grants": grants}


@https_fn.on_call(secrets=ALLOWED_EMAILS_SECRET, invoker="public")
def deny_access_request(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    data = request.data or {}
    request_id = data.get("requestId")
    if not request_id:
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "requestId is required.")

    doc_ref, _ = _get_pending_request(request_id)
    doc_ref.update({"status": "denied", "resolvedAt": firestore.SERVER_TIMESTAMP})
    return {"ok": True}
