"""
API-key generation/hashing. MUST stay byte-for-byte identical to
functions/common.py's hash_api_key/generate_api_key — the CLI writes
apiKeyHash directly to Firestore (Admin SDK, bypassing the Cloud
Functions), and require_api_key in the deployed functions verifies
against that same hash. Duplicated here rather than imported across the
functions/cli package boundary since it's two lines of stdlib-only code.
"""

import hashlib
import secrets


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)
