"""
Admin-SDK Firestore access for the CLI's remote backend. This talks to
Firestore directly (bypassing firestore.rules entirely, same as the
Cloud Functions runtime) rather than calling the deployed HTTPS
functions — the CLI IS a trusted Admin-SDK context, just like the
Functions runtime, so there's no need to round-trip through its own
public API. See docs/OPERATIONS.md for the gitignored service-account
key this requires.
"""

import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

_DEFAULT_KEY_PATH = Path(__file__).parent / "service-account.json"

_app = None


def _key_path() -> Path:
    return Path(os.environ.get("NOTIFRELAY_SERVICE_ACCOUNT", _DEFAULT_KEY_PATH))


def db():
    global _app
    if _app is None:
        key_path = _key_path()
        if not key_path.exists():
            raise SystemExit(
                f"Service-account key not found at {key_path}.\n"
                "See docs/OPERATIONS.md 'Gitignored assets' — generate one from "
                "Firebase console > Project Settings > Service Accounts, or set "
                "NOTIFRELAY_SERVICE_ACCOUNT to point at it."
            )
        _app = firebase_admin.initialize_app(credentials.Certificate(str(key_path)))
    return firestore.client()
