"""
Backend for the e2e test-notification source (android/testapp/) — see
plan "End-to-end verification harness". Posts a real, controllable
notification via the test app's ContentProvider so the real
NotifRelayListenerService picks it up exactly like any other app's
notification, without depending on uncontrollable real third-party apps.
"""

from . import adb_content

AUTHORITY = "com.amaksoft.notifrelay.testapp.provider"


def post_notification(title: str, text: str, channel_id: str) -> None:
    payload = {"title": title, "text": text, "channelId": channel_id}
    adb_content.call(AUTHORITY, "notifications", "post", json=adb_content.b64(payload))
