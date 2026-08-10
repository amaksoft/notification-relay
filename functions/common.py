"""
Shared helpers: Firestore client, owner-email allowlist (Secret Manager
ALLOWED_EMAILS, never hardcoded — see docs/RULE_SCHEMA.md / plan Context),
and subscriber API-key lookup for the client-driven webhook API.
"""

import hashlib
import os
import secrets

from firebase_admin import firestore
from firebase_functions import https_fn
from firebase_functions.https_fn import FunctionsErrorCode, HttpsError

_db = None


def db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db


def _allowed_emails() -> list[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def require_admin(request: https_fn.CallableRequest) -> str:
    """Verify the caller's Firebase ID token belongs to an owner email in
    the ALLOWED_EMAILS secret. Returns the verified email. Every owner-only
    callable in this project takes ALLOWED_EMAILS as a secret and calls
    this first."""
    if request.auth is None:
        raise HttpsError(FunctionsErrorCode.UNAUTHENTICATED, "Sign-in required.")
    email = (request.auth.token.get("email") or "").strip().lower()
    if not email or email not in _allowed_emails():
        raise HttpsError(FunctionsErrorCode.PERMISSION_DENIED, "Not authorized.")
    return email


def hash_api_key(raw_key: str) -> str:
    """One-way hash for storing subscriber API keys at rest. Plaintext is
    only ever shown once, at creation time (see subscribers_callables.py)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def require_api_key(req: https_fn.Request) -> dict:
    """Look up the subscriber for a public API-key-gated HTTPS function
    (webhooks_api.py). Raises via a JSON error response path handled by the
    caller — on_request functions don't get HttpsError's automatic
    handling the way on_call does, so this returns the subscriber dict or
    None and the caller is responsible for producing the 401 response."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    raw_key = auth_header[len("Bearer "):].strip()
    if not raw_key:
        return None
    key_hash = hash_api_key(raw_key)
    query = (
        db()
        .collection("subscribers")
        .where("apiKeyHash", "==", key_hash)
        .where("enabled", "==", True)
        .limit(1)
        .stream()
    )
    for doc in query:
        subscriber = doc.to_dict() or {}
        subscriber["id"] = doc.id
        return subscriber
    return None
