"""
Local/remote backend selection for device-rule commands (see plan CLI
section): if exactly one device is visible over adb, default to it
(instant, works offline); otherwise fall back to Firestore. `--local`/
`--remote` on the CLI overrides the auto-detect.
"""

from . import local_backend, remote_backend
from .config import resolve_device_id


def resolve_mode(prefer: str | None) -> str:
    if prefer in ("local", "remote"):
        if prefer == "local" and not local_backend.adb_available():
            raise SystemExit("--local requested but no single adb device is available.")
        return prefer
    return "local" if local_backend.adb_available() else "remote"


def list_installed_apps(prefer: str | None, device_id: str | None) -> list[dict]:
    mode = resolve_mode(prefer)
    if mode == "local":
        return local_backend.list_installed_apps()
    return remote_backend.list_installed_apps(resolve_device_id(device_id))


def list_seen_channels(prefer: str | None, device_id: str | None, package: str | None) -> list[dict]:
    mode = resolve_mode(prefer)
    if mode == "local":
        return local_backend.list_seen_channels(package)
    return remote_backend.list_seen_channels(resolve_device_id(device_id), package)


def list_rules(prefer: str | None, device_id: str | None) -> list[dict]:
    mode = resolve_mode(prefer)
    if mode == "local":
        return local_backend.list_rules()
    return remote_backend.list_rules(resolve_device_id(device_id))


def add_rule(prefer: str | None, device_id: str | None, rule: dict) -> str:
    mode = resolve_mode(prefer)
    if mode == "local":
        return local_backend.add_rule(rule)
    return remote_backend.add_rule(resolve_device_id(device_id), rule)


def set_rule_enabled(prefer: str | None, device_id: str | None, rule_id: str, enabled: bool) -> None:
    mode = resolve_mode(prefer)
    if mode == "local":
        local_backend.set_rule_enabled(rule_id, enabled)
    else:
        remote_backend.set_rule_enabled(resolve_device_id(device_id), rule_id, enabled)


def remove_rule(prefer: str | None, device_id: str | None, rule_id: str) -> None:
    mode = resolve_mode(prefer)
    if mode == "local":
        local_backend.remove_rule(rule_id)
    else:
        remote_backend.remove_rule(resolve_device_id(device_id), rule_id)
