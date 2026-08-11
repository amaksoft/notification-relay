"""
ingestNotification: the single entry point the phone calls once its
on-device rules have already decided a notification should leave the
device (see plan Architecture overview — this function is the
routing/subscription gate, not the privacy gate; that already happened
on-device before this was ever called).

For every enabled webhook: check the grant pre-filter gate first (is this
(package, channelId) inside the owning subscriber's grant?) — only if
that passes does the webhook's own Condition ever get evaluated. This
ordering is deliberate (see condition_matcher.is_in_grant docstring): it
means no Condition tree, however adversarial, can ever cause a delivery
outside the subscriber's granted scope.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import requests
from firebase_admin import firestore
from firebase_functions import https_fn
from firebase_functions.https_fn import FunctionsErrorCode, HttpsError

from common import db, require_admin
from condition_matcher import is_in_grant, rule_matches, throttle_allows
from webhooks_api import DEFAULT_QUEUE_TTL_SECONDS

DELIVERY_TIMEOUT_SECONDS = 5
DELIVERY_ATTEMPTS = 2

REQUIRED_NOTIFICATION_FIELDS = ("package", "title", "text")


def _validate_notification(data: dict) -> dict:
    notification = data.get("notification")
    if not isinstance(notification, dict):
        raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, "notification object is required.")
    for field in REQUIRED_NOTIFICATION_FIELDS:
        if field not in notification:
            raise HttpsError(FunctionsErrorCode.INVALID_ARGUMENT, f"notification.{field} is required.")
    return notification


def _enabled_subscriber(subscriber_id: str, cache: dict) -> dict | None:
    if subscriber_id in cache:
        return cache[subscriber_id]
    doc = db().collection("subscribers").document(subscriber_id).get()
    subscriber = None
    if doc.exists:
        data = doc.to_dict() or {}
        if data.get("enabled"):
            subscriber = data
    cache[subscriber_id] = subscriber
    return subscriber


def _deliver(webhook: dict, notification: dict, matched_rule_name: str | None) -> tuple[bool, int | None, str | None]:
    payload = {"notification": notification, "matchedRule": matched_rule_name}
    headers = {"Content-Type": "application/json", **(webhook.get("headers") or {})}
    last_error = None
    for attempt in range(DELIVERY_ATTEMPTS):
        try:
            response = requests.post(
                webhook["url"], json=payload, headers=headers, timeout=DELIVERY_TIMEOUT_SECONDS
            )
            return response.ok, response.status_code, None
        except requests.RequestException as exc:
            last_error = str(exc)
            logging.warning("Webhook delivery attempt %d failed for %s: %s", attempt + 1, webhook["url"], exc)
    return False, None, last_error


def _log_delivery(webhook_id: str, subscriber_id: str, notification: dict, matched_rule_name: str | None,
                   success: bool, http_code: int | None, error: str | None) -> None:
    db().collection("delivery_log").document().set(
        {
            "webhookId": webhook_id,
            "subscriberId": subscriber_id,
            "notificationSummary": {
                "package": notification.get("package"),
                "channelId": notification.get("channelId"),
                "deviceId": notification.get("deviceId"),
                "title": notification.get("title"),
            },
            "matchedRule": matched_rule_name,
            "status": "delivered" if success else "failed",
            "httpCode": http_code,
            "error": error,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )


def _enqueue_for_poll(webhook_id: str, subscriber_id: str, notification: dict,
                       matched_rule_name: str | None, queue_ttl_seconds: int) -> None:
    """Fallback for when the real-time push attempt failed (see
    webhooks_api.DEFAULT_QUEUE_TTL_SECONDS docstring) — only ever called on
    push failure, never on success, so a subscriber gets exactly one
    delivery: push if they were up, poll if they weren't. `expiresAt` must
    stay an actual Firestore Timestamp (not a raw number) — that's a hard
    requirement for Firestore's native per-collection TTL policy (see
    OPERATIONS.md) to pick this field up at all; webhooks_api._poll_queue's
    own query (expiresAt > now) is still the real correctness boundary
    though, since that native sweep can lag up to ~24h and only exists for
    storage cleanup of never-polled items."""
    db().collection("webhook_queue").document().set(
        {
            "webhookId": webhook_id,
            "subscriberId": subscriber_id,
            "notification": notification,
            "matchedRule": matched_rule_name,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "expiresAt": datetime.now(timezone.utc) + timedelta(seconds=queue_ttl_seconds),
        }
    )


@https_fn.on_call(secrets=["ALLOWED_EMAILS"], invoker="public")
def ingest_notification(request: https_fn.CallableRequest) -> dict:
    require_admin(request)
    notification = _validate_notification(request.data or {})

    now = time.time()
    subscriber_cache: dict = {}
    matched = []
    webhook_docs = list(db().collection("webhooks").stream())

    for doc in webhook_docs:
        webhook_id = doc.id
        try:
            webhook = doc.to_dict() or {}
            filter_rule = webhook.get("filter") or {}
            subscriber_id = webhook.get("subscriberId")

            subscriber = _enabled_subscriber(subscriber_id, subscriber_cache) if subscriber_id else None
            if subscriber is None:
                continue

            if not is_in_grant(
                notification["package"], notification.get("channelId"), notification.get("deviceId"),
                subscriber.get("grants"),
            ):
                continue

            if not rule_matches(filter_rule, notification):
                continue

            throttle_seconds = filter_rule.get("throttleSeconds", 0)
            last_fired_at = webhook.get("lastFiredAt")
            if not throttle_allows(last_fired_at, throttle_seconds, now):
                continue

            doc.reference.update({"lastFiredAt": now})
            matched_rule_name = filter_rule.get("name")
            success, http_code, error = _deliver(webhook, notification, matched_rule_name)
            _log_delivery(webhook_id, subscriber_id, notification, matched_rule_name, success, http_code, error)
            matched.append({"webhookId": webhook_id, "delivered": success})
            if not success:
                logging.error(
                    "Webhook delivery exhausted retries: webhook=%s subscriber=%s url=%s httpCode=%s error=%s",
                    webhook_id, subscriber_id, webhook.get("url"), http_code, error,
                )
                queue_ttl_seconds = webhook.get("queueTtlSeconds") or DEFAULT_QUEUE_TTL_SECONDS
                _enqueue_for_poll(webhook_id, subscriber_id, notification, matched_rule_name, queue_ttl_seconds)
                logging.info(
                    "Queued for poll fallback: webhook=%s subscriber=%s ttlSeconds=%d",
                    webhook_id, subscriber_id, queue_ttl_seconds,
                )
        except Exception:
            # One malformed/misbehaving webhook (e.g. a subscriber-submitted
            # filter with an invalid Condition shape) must never abort
            # delivery to every other webhook in this loop — log it as a
            # real error (picked up by Cloud Error Reporting) and move on.
            logging.exception("Unexpected error processing webhook %s during ingest", webhook_id)

    logging.info(
        "ingest_notification: package=%s channelId=%s webhooksConsidered=%d matched=%d",
        notification.get("package"), notification.get("channelId"), len(webhook_docs), len(matched),
    )
    return {"matched": len(matched), "results": matched}
