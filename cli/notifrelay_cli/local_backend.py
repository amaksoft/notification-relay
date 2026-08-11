"""
adb/ContentProvider ("local") backend — device rules/apps/channels only;
subscriber and webhook management stay Firestore-only (see plan: the CLI
is access management, subscribers/webhooks aren't a device-side concept
at all). Talks to the main app's ContentProvider — see adb_content.py's
module docstring for the wire-format rationale this depends on.
"""

from . import adb_content

AUTHORITY = "com.amaksoft.notifrelay.provider"


def adb_available() -> bool:
    return adb_content.adb_available()


def list_installed_apps() -> list[dict]:
    return adb_content.query(AUTHORITY, "apps", "appJson")


def list_seen_channels(package: str | None = None) -> list[dict]:
    channels = adb_content.query(AUTHORITY, "channels", "channelJson")
    if package:
        channels = [c for c in channels if c.get("package") == package]
    return channels


def list_rules() -> list[dict]:
    return adb_content.query(AUTHORITY, "rules", "ruleJson")


def add_rule(rule: dict) -> str:
    rule = {"enabled": True, "throttleSeconds": 0, "order": 0, "format": "DEFAULT", **rule}
    adb_content.call(AUTHORITY, "rules", "addRule", json=adb_content.b64(rule))
    # The provider assigns the id and is the source of truth; re-read to report it back.
    matches = [r for r in list_rules() if r.get("name") == rule.get("name")]
    return matches[-1]["id"] if matches else ""


def set_rule_enabled(rule_id: str, enabled: bool) -> None:
    adb_content.call(AUTHORITY, "rules", "setRuleEnabled", json=adb_content.b64({"id": rule_id, "enabled": enabled}))


def remove_rule(rule_id: str) -> None:
    adb_content.call(AUTHORITY, "rules", "removeRule", json=adb_content.b64({"id": rule_id}))
