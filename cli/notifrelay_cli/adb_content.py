"""
Generic adb/ContentProvider helpers shared by local_backend.py (main app)
and testapp_backend.py (e2e test-notification source). See
local_backend.py's module docstring for the wire-format rationale
(single-JSON-column query rows, base64-encoded call() writes).
"""

import base64
import json
import subprocess


def uri(authority: str, path: str) -> str:
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


def query(authority: str, path: str, column: str) -> list[dict]:
    result = subprocess.run(
        ["adb", "shell", "content", "query", "--uri", uri(authority, path), "--projection", column],
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


def call(authority: str, path: str, method: str, **extras: str) -> None:
    args = ["adb", "shell", "content", "call", "--uri", uri(authority, path), "--method", method]
    for key, value in extras.items():
        args += ["--extra", f"{key}:s:{value}"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise SystemExit(f"adb content call failed: {result.stderr.strip() or result.stdout.strip()}")


def b64(data: dict) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")
