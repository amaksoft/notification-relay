"""
Automated end-to-end verification harness for the notification-relay
backend — see docs/OPERATIONS.md "End-to-end verification" and the plan's
"End-to-end verification harness" section.

Exercises the server side of the pipe (grant gate, Condition matching,
push delivery, poll-queue fallback) by calling `ingest_notification`
directly with a real owner-signed ID token, exactly as the phone would —
this is deliberately NOT routed through a physical device/testapp, since
everything this script checks lives entirely in the backend and doesn't
need one. (Device-side capture — NotificationListenerService actually
seeing a real Android notification and building this same payload — is
still only verifiable on real hardware; see docs/OPERATIONS.md.)

Requires cli/notifrelay_cli/service-account.json (Admin SDK) with
Firebase Auth admin access to mint a custom token for the owner account,
and the project's web API key to exchange it for a real ID token via the
Identity Toolkit REST API.

Run: python3 e2e/run_e2e.py
"""

import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from firebase_admin import auth
from google.cloud.firestore_v1 import FieldFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))

from notifrelay_cli import remote_backend  # noqa: E402
from notifrelay_cli.firestore_client import db  # noqa: E402

PROJECT_ID = "notification-relay-73586"
WEB_API_KEY = "AIzaSyBoojhp-hM-i3NvrAVT2xlEjEh5qOhT8_g"
OWNER_EMAIL = "amaksoft@gmail.com"
FUNCTIONS_BASE = f"https://us-central1-{PROJECT_ID}.cloudfunctions.net"

TEST_PACKAGE = "com.amaksoft.notifrelay.testapp"
TEST_RECEIVER_URL = f"{FUNCTIONS_BASE}/test_receiver"
# Used to deliberately force a push-delivery failure for the poll-queue
# scenario, without needing an actually-unreachable endpoint
# (validate_webhook_url requires a real, resolvable https host). Hitting
# our own webhooks_api function with no Authorization header reliably
# returns 401 — self-contained (no third-party dependency) and avoids the
# Hosting catch-all SPA rewrite ("**" -> /index.html), which would make
# any nonexistent path on the .web.app domain return 200, not 404.
FORCED_FAILURE_URL = f"{FUNCTIONS_BASE}/webhooks_api"


def notification(channel_id: str, device_id: str, title: str = "e2e") -> dict:
    return {
        "package": TEST_PACKAGE,
        "appName": "NotifRelay Test",
        "title": title,
        "text": "e2e test notification",
        "channelId": channel_id,
        "channelName": channel_id,
        "flags": 0,
        "importance": 3,
        "deviceId": device_id,
    }


def get_owner_id_token() -> str:
    uid = auth.get_user_by_email(OWNER_EMAIL).uid
    custom_token = auth.create_custom_token(uid).decode("utf-8")
    resp = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={WEB_API_KEY}",
        json={"token": custom_token, "returnSecureToken": True},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["idToken"]


def call_ingest(id_token: str, notif: dict) -> dict:
    resp = requests.post(
        f"{FUNCTIONS_BASE}/ingest_notification",
        json={"data": {"notification": notif}},
        headers={"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"ingest_notification error: {body['error']}")
    return body["result"]


def register_webhook(api_key: str, condition: dict, url: str = TEST_RECEIVER_URL, queue_ttl_seconds: int | None = None) -> str:
    body = {"url": url, "filter": {"condition": condition, "enabled": True}}
    if queue_ttl_seconds is not None:
        body["queueTtlSeconds"] = queue_ttl_seconds
    resp = requests.post(
        f"{FUNCTIONS_BASE}/webhooks_api",
        json=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def poll_queue(api_key: str, webhook_id: str) -> list[dict]:
    resp = requests.get(
        f"{FUNCTIONS_BASE}/webhooks_api/{webhook_id}/queue",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["items"]


def submit_access_request(api_key: str, grants: list[dict], note: str = "") -> str:
    resp = requests.post(
        f"{FUNCTIONS_BASE}/access_requests_api",
        json={"grants": grants, "note": note},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


class Cleanup:
    """Collected in reverse order and always run, even on failure —
    mirrors the plan's 'explicit cleanup in a finally/trap' requirement."""

    def __init__(self):
        self.actions = []

    def add(self, fn):
        self.actions.append(fn)

    def run(self):
        for fn in reversed(self.actions):
            try:
                fn()
            except Exception:
                print(f"  (cleanup warning: {fn} failed)")
                traceback.print_exc()


def scenario_channel_grant(id_token: str, cleanup: Cleanup) -> None:
    """Regression check: channel-scoped grant allows the granted channel
    and excludes others (the original e2e case, now scripted)."""
    device_id = "e2e-device-a"
    sub_id, api_key = remote_backend.create_subscriber(
        "e2e-channel-grant", {"grants": [{"package": TEST_PACKAGE, "channelIds": ["test_channel_a"]}]}, ttl_seconds=600
    )
    cleanup.add(lambda: remote_backend.delete_subscriber(sub_id))
    register_webhook(api_key, {"type": "ALWAYS"})

    result = call_ingest(id_token, notification("test_channel_a", device_id))
    assert result["matched"] == 1, f"expected 1 match for granted channel, got {result}"
    assert result["results"][0]["delivered"] is True, f"expected delivery to succeed, got {result}"

    result = call_ingest(id_token, notification("test_channel_b", device_id))
    assert result["matched"] == 0, f"expected 0 matches for ungranted channel, got {result}"


def scenario_device_grant(id_token: str, cleanup: Cleanup) -> None:
    """Owner-controlled device scoping: a grant restricted to deviceIds
    only lets that device's notifications through, even though the
    package/channel are otherwise unrestricted."""
    sub_id, api_key = remote_backend.create_subscriber(
        "e2e-device-grant",
        {"grants": [{"package": TEST_PACKAGE, "channelIds": ["test_channel_a"], "deviceIds": ["device-x"]}]},
        ttl_seconds=600,
    )
    cleanup.add(lambda: remote_backend.delete_subscriber(sub_id))
    register_webhook(api_key, {"type": "ALWAYS"})

    result = call_ingest(id_token, notification("test_channel_a", "device-x"))
    assert result["matched"] == 1, f"expected match for granted device, got {result}"
    assert result["results"][0]["delivered"] is True

    result = call_ingest(id_token, notification("test_channel_a", "device-y"))
    assert result["matched"] == 0, f"expected no match for ungranted device, got {result}"


def scenario_device_condition_leaf(id_token: str, cleanup: Cleanup) -> None:
    """Self-service device filtering: grant allows the whole package (any
    device), but the subscriber's own webhook Condition further narrows
    to one device via NOTIFICATION_DEVICE_ID."""
    sub_id, api_key = remote_backend.create_subscriber(
        "e2e-device-filter", {"grants": [{"package": TEST_PACKAGE}]}, ttl_seconds=600
    )
    cleanup.add(lambda: remote_backend.delete_subscriber(sub_id))
    condition = {
        "type": "AND",
        "conditions": [
            {"type": "NOTIFICATION_PACKAGE_NAME", "stringValue": TEST_PACKAGE},
            {"type": "NOTIFICATION_DEVICE_ID", "stringValue": "device-x"},
        ],
    }
    register_webhook(api_key, condition)

    result = call_ingest(id_token, notification("test_channel_a", "device-x"))
    assert result["matched"] == 1, f"expected the webhook's own filter to match device-x, got {result}"
    assert result["results"][0]["delivered"] is True

    result = call_ingest(id_token, notification("test_channel_a", "device-y"))
    assert result["matched"] == 0, (
        f"expected the webhook's own filter to reject device-y (even though the grant allows the "
        f"whole package), got {result}"
    )


def scenario_batch_grant(cleanup: Cleanup) -> None:
    """Multiple (package, channelIds, deviceIds) grants in a single call."""
    sub_id, _ = remote_backend.create_subscriber("e2e-batch-grant", {"grants": []}, ttl_seconds=600)
    cleanup.add(lambda: remote_backend.delete_subscriber(sub_id))

    grants = remote_backend.grant_access(
        sub_id,
        [
            {"package": "com.slack"},
            {"package": "com.whatsapp", "channelIds": ["calls_channel"], "deviceIds": ["pixel-8"]},
        ],
    )
    packages = {g["package"] for g in grants["grants"]}
    assert packages == {"com.slack", "com.whatsapp"}, f"expected both packages granted in one call, got {grants}"
    whatsapp_grant = next(g for g in grants["grants"] if g["package"] == "com.whatsapp")
    assert whatsapp_grant.get("channelIds") == ["calls_channel"]
    assert whatsapp_grant.get("deviceIds") == ["pixel-8"]


def scenario_access_requests(id_token: str, cleanup: Cleanup) -> None:
    """Submit -> approve merges the grant and unlocks delivery; a second
    submit -> deny leaves the subscriber's grants untouched."""
    device_id = "e2e-device-a"
    sub_id, api_key = remote_backend.create_subscriber("e2e-access-request", {"grants": []}, ttl_seconds=600)
    cleanup.add(lambda: remote_backend.delete_subscriber(sub_id))
    register_webhook(api_key, {"type": "ALWAYS"})

    # Not granted yet — nothing should be delivered.
    result = call_ingest(id_token, notification("test_channel_a", device_id))
    assert result["matched"] == 0, f"expected no match before any grant, got {result}"

    approve_id = submit_access_request(
        api_key, [{"package": TEST_PACKAGE, "channelIds": ["test_channel_a"]}], note="e2e approve case"
    )
    pending = remote_backend.list_access_requests("pending")
    assert any(r["id"] == approve_id for r in pending), "submitted request not found in pending list"

    remote_backend.approve_access_request(approve_id)
    result = call_ingest(id_token, notification("test_channel_a", device_id))
    assert result["matched"] == 1, f"expected delivery after approval, got {result}"

    deny_id = submit_access_request(api_key, [{"package": "com.unrelated.app"}], note="e2e deny case")
    remote_backend.deny_access_request(deny_id)
    subs = {s["id"]: s for s in remote_backend.list_subscribers()}
    packages = {g["package"] for g in subs[sub_id]["grants"].get("grants", [])}
    assert "com.unrelated.app" not in packages, "denied request must not have merged into grants"


def scenario_hard_delete(cleanup: Cleanup) -> None:
    """Deleting a subscriber removes the subscriber doc, its webhooks,
    and every collection that references it by subscriberId."""
    sub_id, api_key = remote_backend.create_subscriber(
        "e2e-hard-delete", {"grants": [{"package": TEST_PACKAGE}]}, ttl_seconds=600
    )
    register_webhook(api_key, {"type": "ALWAYS"})
    submit_access_request(api_key, [{"package": "com.example"}])

    remote_backend.delete_subscriber(sub_id)

    assert not db().collection("subscribers").document(sub_id).get().exists
    for collection in ("webhooks", "access_requests"):
        remaining = list(db().collection(collection).where(filter=FieldFilter("subscriberId", "==", sub_id)).stream())
        assert remaining == [], f"{collection} still has docs referencing deleted subscriber {sub_id}: {remaining}"
    # Already deleted above — nothing left for the outer cleanup to do,
    # but registering a no-op keeps this scenario's shape consistent with
    # the others (and guards against a future edit reordering things).
    cleanup.add(lambda: None)


def scenario_ttl_queue(id_token: str, cleanup: Cleanup) -> None:
    """Push delivery to an endpoint that will fail falls back to the poll
    queue; the item is returned exactly once (pop semantics), and an
    already-expired item is never returned regardless of whether
    Firestore's background TTL sweep has physically deleted it yet."""
    device_id = "e2e-device-a"
    sub_id, api_key = remote_backend.create_subscriber(
        "e2e-ttl-queue", {"grants": [{"package": TEST_PACKAGE, "channelIds": ["test_channel_a"]}]}, ttl_seconds=600
    )
    cleanup.add(lambda: remote_backend.delete_subscriber(sub_id))
    webhook_id = register_webhook(api_key, {"type": "ALWAYS"}, url=FORCED_FAILURE_URL, queue_ttl_seconds=120)

    result = call_ingest(id_token, notification("test_channel_a", device_id, title="queued-item"))
    assert result["matched"] == 1
    assert result["results"][0]["delivered"] is False, "expected push delivery to this 404 URL to fail"

    items = poll_queue(api_key, webhook_id)
    assert len(items) == 1, f"expected exactly 1 queued item after the failed push, got {items}"
    assert items[0]["notification"]["title"] == "queued-item"

    items_again = poll_queue(api_key, webhook_id)
    assert items_again == [], f"expected the queue to be empty after popping once, got {items_again}"

    # Seed an already-expired item directly (waiting out a real TTL would
    # make this script slow) and confirm the poll query's own expiresAt
    # filter excludes it — that filter, not the native TTL sweep, is the
    # actual correctness boundary (see docs/OPERATIONS.md).
    expired_ref = db().collection("webhook_queue").document()
    expired_ref.set(
        {
            "webhookId": webhook_id,
            "subscriberId": sub_id,
            "notification": notification("test_channel_a", device_id, title="already-expired"),
            "matchedRule": None,
            "createdAt": datetime.now(timezone.utc) - timedelta(seconds=10),
            "expiresAt": datetime.now(timezone.utc) - timedelta(seconds=5),
        }
    )
    items_expired = poll_queue(api_key, webhook_id)
    assert items_expired == [], f"expected an already-expired item to be excluded from poll results, got {items_expired}"
    expired_ref.delete()  # the poll query correctly skipped it, so it's still there — clean it up ourselves


SCENARIOS = [
    ("channel grant (regression)", lambda id_token, c: scenario_channel_grant(id_token, c)),
    ("device-scoped grant", lambda id_token, c: scenario_device_grant(id_token, c)),
    ("NOTIFICATION_DEVICE_ID condition leaf", lambda id_token, c: scenario_device_condition_leaf(id_token, c)),
    ("batch grant", lambda id_token, c: scenario_batch_grant(c)),
    ("access requests: submit/approve/deny", lambda id_token, c: scenario_access_requests(id_token, c)),
    ("hard delete cascades", lambda id_token, c: scenario_hard_delete(c)),
    ("TTL poll-queue fallback", lambda id_token, c: scenario_ttl_queue(id_token, c)),
]


def main() -> int:
    db()  # force firebase_admin app init before auth.* calls need it
    print("Minting owner ID token...")
    id_token = get_owner_id_token()

    failures = 0
    for name, fn in SCENARIOS:
        cleanup = Cleanup()
        start = time.monotonic()
        try:
            fn(id_token, cleanup)
            print(f"PASS  {name}  ({time.monotonic() - start:.1f}s)")
        except Exception as exc:
            failures += 1
            print(f"FAIL  {name}  ({time.monotonic() - start:.1f}s): {exc}")
            traceback.print_exc()
        finally:
            cleanup.run()

    print(f"\n{len(SCENARIOS) - failures}/{len(SCENARIOS)} scenarios passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
