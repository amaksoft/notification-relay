"""
adb/ContentProvider ("local") backend — device rules/apps/channels only;
subscriber and webhook management stay Firestore-only (see plan: the CLI
is access management, subscribers/webhooks aren't a device-side concept
at all). Talks to the Android app's ContentProvider, built in a later
step (task 7) — this module defines the contract that provider must
honor:

- Reads use `content query --projection <col>` returning ONE JSON-blob
  column per row (`ruleJson` / `appJson` / `channelJson`). A generic
  multi-column `Row: 0 a=.., b=..` text format is unparseable once any
  column (like a Condition tree) can itself contain commas/equals signs,
  so the provider deliberately serializes each row as a single JSON
  string instead of spreading it across real columns.
- Writes use `content call --method <name> --extra json:s:<base64>`,
  base64-encoding the JSON payload rather than passing it as a raw
  --extra value: `adb shell` joins all arguments into one string and
  re-tokenizes it on the device, so anything with spaces/quotes/colons
  (any real JSON) would otherwise get mangled in transit. The provider's
  call() must base64-decode `json` before parsing it.

This is untested against a real device until the Android ContentProvider
in task 7 exists — it's written directly against the interface documented
in the plan/RULE_SCHEMA.md so the two sides are unambiguous about the
wire format.
"""

import base64
import json
import subprocess

MAIN_APP_AUTHORITY = "com.amaksoft.notifrelay.provider"


def _uri(path: str, authority: str = MAIN_APP_AUTHORITY) -> str:
    return f"content://{authority}/{path}"


def adb_available() -> bool:
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    lines = [
        line for line in result.stdout.splitlines()[1:]
        if line.strip() and line.split()[-1] == "device"
    ]
    return len(lines) == 1


def _query(path: str, column: str) -> list[dict]:
    result = subprocess.run(
        ["adb", "shell", "content", "query", "--uri", _uri(path), "--projection", column],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise SystemExit(f"adb content query failed: {result.stderr.strip() or result.stdout.strip()}")
    rows = []
    marker = f"{column}="
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        idx = line.find(marker)
        if idx == -1:
            continue
        rows.append(json.loads(line[idx + len(marker):]))
    return rows


def _call(path: str, method: str, **extras: str) -> None:
    args = ["adb", "shell", "content", "call", "--uri", _uri(path), "--method", method]
    for key, value in extras.items():
        args += ["--extra", f"{key}:s:{value}"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise SystemExit(f"adb content call failed: {result.stderr.strip() or result.stdout.strip()}")


def _b64(data: dict) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")


def list_installed_apps() -> list[dict]:
    return _query("apps", "appJson")


def list_seen_channels(package: str | None = None) -> list[dict]:
    channels = _query("channels", "channelJson")
    if package:
        channels = [c for c in channels if c.get("package") == package]
    return channels


def list_rules() -> list[dict]:
    return _query("rules", "ruleJson")


def add_rule(rule: dict) -> str:
    rule = {"enabled": True, "throttleSeconds": 0, "order": 0, "format": "DEFAULT", **rule}
    _call("rules", "addRule", json=_b64(rule))
    # The provider assigns the id and is the source of truth; re-read to report it back.
    matches = [r for r in list_rules() if r.get("name") == rule.get("name")]
    return matches[-1]["id"] if matches else ""


def set_rule_enabled(rule_id: str, enabled: bool) -> None:
    _call("rules", "setRuleEnabled", json=_b64({"id": rule_id, "enabled": enabled}))


def remove_rule(rule_id: str) -> None:
    _call("rules", "removeRule", json=_b64({"id": rule_id}))
