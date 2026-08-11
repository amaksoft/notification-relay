"""
Small local CLI config: a default device id (set via `notifrelay device
use <id>`) so day-to-day commands don't need --device-id every time once
you've got one phone set up. Lives outside the repo/gitignored areas
entirely, in the user's own config dir — this is local CLI preference,
not project state.
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("NOTIFRELAY_CONFIG_DIR", Path.home() / ".config" / "notifrelay"))
CONFIG_FILE = CONFIG_DIR / "config.json"


def _read() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    return json.loads(CONFIG_FILE.read_text())


def _write(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_default_device_id() -> str | None:
    return _read().get("defaultDeviceId")


def set_default_device_id(device_id: str) -> None:
    data = _read()
    data["defaultDeviceId"] = device_id
    _write(data)


def resolve_device_id(explicit: str | None) -> str:
    device_id = explicit or get_default_device_id()
    if not device_id:
        raise SystemExit(
            "No device id given and no default set. Pass --device-id, or run "
            "`notifrelay device use <id>` once you know it."
        )
    return device_id
