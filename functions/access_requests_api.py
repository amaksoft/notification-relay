"""
Public, API-key-gated access-request submission — the self-service half
of the plan divergence: API keys stay owner-issued only (unchanged), but
a subscriber holding one can now request additional (package, channelIds,
deviceIds) grants themselves instead of the owner running a CLI command
based on some out-of-band ask. The owner still controls the outcome
entirely — see access_requests_callables.py for the approve/deny side,
which is the only thing that actually touches a subscriber's grants.
"""

from firebase_admin import firestore
from firebase_functions import https_fn
from google.cloud.firestore_v1 import FieldFilter

from common import cors_preflight, db, json_response, require_api_key

MAX_PENDING_REQUESTS_PER_SUBSCRIBER = 10


def _validate_grants(grants) -> str | None:
    if not isinstance(grants, list) or not grants:
        return "grants (non-empty array) is required."
    for entry in grants:
        if not isinstance(entry, dict) or not entry.get("package"):
            return "each grant entry needs a package."
    return None


@https_fn.on_request(invoker="public")
def access_requests_api(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return cors_preflight()

    subscriber = require_api_key(req)
    if subscriber is None:
        return json_response({"error": "Invalid or missing API key."}, 401)
    subscriber_id = subscriber["id"]

    if req.method == "GET":
        requests_ = []
        for doc in (
            db().collection("access_requests")
            .where(filter=FieldFilter("subscriberId", "==", subscriber_id))
            .stream()
        ):
            entry = doc.to_dict() or {}
            entry["id"] = doc.id
            requests_.append(entry)
        return json_response({"requests": requests_})

    if req.method == "POST":
        pending_count = len(
            list(
                db().collection("access_requests")
                .where(filter=FieldFilter("subscriberId", "==", subscriber_id))
                .where(filter=FieldFilter("status", "==", "pending"))
                .stream()
            )
        )
        if pending_count >= MAX_PENDING_REQUESTS_PER_SUBSCRIBER:
            return json_response(
                {"error": f"Too many pending requests ({MAX_PENDING_REQUESTS_PER_SUBSCRIBER}). Wait for the owner to review them."},
                400,
            )

        body = req.get_json(silent=True) or {}
        grants = body.get("grants")
        error = _validate_grants(grants)
        if error:
            return json_response({"error": error}, 400)

        doc_ref = db().collection("access_requests").document()
        doc_ref.set(
            {
                "subscriberId": subscriber_id,
                "subscriberName": subscriber.get("name"),
                "grants": grants,
                "note": (body.get("note") or "").strip()[:500],
                "status": "pending",
                "createdAt": firestore.SERVER_TIMESTAMP,
                "resolvedAt": None,
            }
        )
        return json_response({"id": doc_ref.id}, 201)

    return json_response({"error": "Not found."}, 404)
