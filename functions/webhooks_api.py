"""
Public, API-key-gated webhook CRUD. Fully client-driven (see plan
Context): a subscriber authors and owns their own webhooks entirely —
this module never checks whether a submitted Condition tree "fits" the
subscriber's grant (see condition_matcher.is_in_grant docstring for why
that's deliberately NOT done here); grant enforcement happens once, at
fan-out time in ingest.py.

Single on_request function, manually routed by path/method since
external subscribers authenticate with a bearer API key, not Firebase
Auth — there's no Callable SDK identity to hang this off of.
"""

from firebase_admin import firestore
from firebase_functions import https_fn

from common import cors_preflight, db, json_response, require_api_key, validate_webhook_url

MAX_WEBHOOKS_PER_SUBSCRIBER = 20


def _route(req: https_fn.Request) -> tuple[str | None, str | None]:
    segments = [s for s in req.path.split("/") if s]
    try:
        idx = segments.index("webhooks")
    except ValueError:
        return None, None
    rest = segments[idx + 1:]
    webhook_id = rest[0] if len(rest) >= 1 else None
    action = rest[1] if len(rest) >= 2 else None
    return webhook_id, action


def _validate_filter(filter_data) -> str | None:
    if not isinstance(filter_data, dict):
        return "filter is required."
    condition = filter_data.get("condition")
    if not isinstance(condition, dict) or not condition.get("type"):
        return "filter.condition with a type is required."
    return None


def _own_webhook_or_none(webhook_id: str, subscriber_id: str):
    doc = db().collection("webhooks").document(webhook_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if data.get("subscriberId") != subscriber_id:
        return None
    return doc


def _list_webhooks(subscriber_id: str) -> https_fn.Response:
    webhooks = []
    for doc in db().collection("webhooks").where("subscriberId", "==", subscriber_id).stream():
        entry = doc.to_dict() or {}
        entry["id"] = doc.id
        webhooks.append(entry)
    return json_response({"webhooks": webhooks})


def _create_webhook(req: https_fn.Request, subscriber_id: str) -> https_fn.Response:
    existing_count = len(
        list(db().collection("webhooks").where("subscriberId", "==", subscriber_id).stream())
    )
    if existing_count >= MAX_WEBHOOKS_PER_SUBSCRIBER:
        return json_response({"error": f"Webhook limit ({MAX_WEBHOOKS_PER_SUBSCRIBER}) reached."}, 400)

    body = req.get_json(silent=True) or {}
    url = body.get("url")
    if not url:
        return json_response({"error": "url is required."}, 400)
    url_error = validate_webhook_url(url)
    if url_error:
        return json_response({"error": url_error}, 400)

    filter_error = _validate_filter(body.get("filter"))
    if filter_error:
        return json_response({"error": filter_error}, 400)

    doc_ref = db().collection("webhooks").document()
    doc_ref.set(
        {
            "subscriberId": subscriber_id,
            "url": url,
            "headers": body.get("headers") or {},
            "filter": body["filter"],
            "createdAt": firestore.SERVER_TIMESTAMP,
        }
    )
    return json_response({"id": doc_ref.id}, 201)


def _update_webhook(req: https_fn.Request, subscriber_id: str, webhook_id: str) -> https_fn.Response:
    doc = _own_webhook_or_none(webhook_id, subscriber_id)
    if doc is None:
        return json_response({"error": "Webhook not found."}, 404)

    body = req.get_json(silent=True) or {}
    update = {}
    if "url" in body:
        url_error = validate_webhook_url(body["url"])
        if url_error:
            return json_response({"error": url_error}, 400)
        update["url"] = body["url"]
    if "headers" in body:
        update["headers"] = body["headers"] or {}
    if "filter" in body:
        filter_error = _validate_filter(body["filter"])
        if filter_error:
            return json_response({"error": filter_error}, 400)
        update["filter"] = body["filter"]

    if not update:
        return json_response({"error": "No updatable fields provided."}, 400)

    doc.reference.update(update)
    return json_response({"ok": True})


def _delete_webhook(subscriber_id: str, webhook_id: str) -> https_fn.Response:
    doc = _own_webhook_or_none(webhook_id, subscriber_id)
    if doc is None:
        return json_response({"error": "Webhook not found."}, 404)
    doc.reference.delete()
    return json_response({"ok": True})


def _test_webhook(subscriber_id: str, webhook_id: str) -> https_fn.Response:
    import requests

    doc = _own_webhook_or_none(webhook_id, subscriber_id)
    if doc is None:
        return json_response({"error": "Webhook not found."}, 404)
    webhook = doc.to_dict() or {}

    sample_notification = {
        "package": "com.example.test",
        "title": "Test notification",
        "text": "This is a test delivery from notification-relay.",
        "channelId": "test",
    }
    headers = {"Content-Type": "application/json", **(webhook.get("headers") or {})}
    try:
        response = requests.post(
            webhook["url"], json={"notification": sample_notification, "matchedRule": "test"},
            headers=headers, timeout=5,
        )
        return json_response({"ok": response.ok, "httpCode": response.status_code})
    except requests.RequestException as exc:
        return json_response({"ok": False, "error": str(exc)}, 502)


@https_fn.on_request()
def webhooks_api(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return cors_preflight()

    subscriber = require_api_key(req)
    if subscriber is None:
        return json_response({"error": "Invalid or missing API key."}, 401)
    subscriber_id = subscriber["id"]

    webhook_id, action = _route(req)

    if webhook_id is None and req.method == "GET":
        return _list_webhooks(subscriber_id)
    if webhook_id is None and req.method == "POST":
        return _create_webhook(req, subscriber_id)
    if webhook_id and action == "test" and req.method == "POST":
        return _test_webhook(subscriber_id, webhook_id)
    if webhook_id and action is None and req.method == "PATCH":
        return _update_webhook(req, subscriber_id, webhook_id)
    if webhook_id and action is None and req.method == "DELETE":
        return _delete_webhook(subscriber_id, webhook_id)

    return json_response({"error": "Not found."}, 404)
