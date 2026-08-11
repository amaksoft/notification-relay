"""
Self-hosted webhook target for the e2e verification harness (see plan
"End-to-end verification harness"). A real subscriber webhook, registered
by the e2e script itself, pointing back at our own infrastructure — logs
whatever it receives into `test_deliveries` so the e2e script can assert
on delivery (and non-delivery, for the grant-exclusion check) without
needing ngrok/webhook.site or any other external dependency.
"""

from firebase_admin import firestore
from firebase_functions import https_fn

from common import cors_preflight, db, json_response


@https_fn.on_request(invoker="public")
def test_receiver(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return cors_preflight()

    body = req.get_json(silent=True) or {}
    db().collection("test_deliveries").document().set(
        {
            "notification": body.get("notification"),
            "matchedRule": body.get("matchedRule"),
            "receivedAt": firestore.SERVER_TIMESTAMP,
        }
    )
    return json_response({"ok": True})
