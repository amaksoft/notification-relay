import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import validate_webhook_url  # noqa: E402
from webhooks_api import _route, _validate_filter  # noqa: E402


class FakeRequest:
    def __init__(self, path):
        self.path = path


class TestValidateWebhookUrl:
    def test_valid_https_url_ok(self):
        assert validate_webhook_url("https://example.com/hook") is None

    def test_http_rejected(self):
        assert validate_webhook_url("http://example.com/hook") is not None

    def test_localhost_rejected(self):
        assert validate_webhook_url("https://localhost/hook") is not None

    def test_loopback_ip_rejected(self):
        assert validate_webhook_url("https://127.0.0.1/hook") is not None

    def test_private_ip_rejected(self):
        assert validate_webhook_url("https://10.0.0.5/hook") is not None
        assert validate_webhook_url("https://192.168.1.1/hook") is not None

    def test_link_local_metadata_ip_rejected(self):
        # cloud metadata endpoint IP — classic SSRF target
        assert validate_webhook_url("https://169.254.169.254/hook") is not None

    def test_metadata_hostname_rejected(self):
        assert validate_webhook_url("https://metadata.google.internal/hook") is not None

    def test_dot_local_rejected(self):
        assert validate_webhook_url("https://myphone.local/hook") is not None

    def test_public_ip_literal_allowed(self):
        assert validate_webhook_url("https://8.8.8.8/hook") is None

    def test_missing_hostname_rejected(self):
        assert validate_webhook_url("https:///hook") is not None

    def test_unparseable_scheme_rejected(self):
        assert validate_webhook_url("ftp://example.com/hook") is not None


class TestRoute:
    def test_list_or_create_path(self):
        assert _route(FakeRequest("/api/webhooks")) == (None, None)

    def test_single_webhook_path(self):
        assert _route(FakeRequest("/api/webhooks/abc123")) == ("abc123", None)

    def test_test_action_path(self):
        assert _route(FakeRequest("/api/webhooks/abc123/test")) == ("abc123", "test")

    def test_raw_function_url_no_webhooks_segment(self):
        # Hitting the function directly (not via the Hosting /api/webhooks
        # rewrite) never has a literal "webhooks" path segment at all —
        # routing must still work identically in that case.
        assert _route(FakeRequest("/")) == (None, None)
        assert _route(FakeRequest("/abc123")) == ("abc123", None)
        assert _route(FakeRequest("/abc123/test")) == ("abc123", "test")


class TestValidateFilter:
    def test_valid_filter(self):
        assert _validate_filter({"condition": {"type": "ALWAYS"}}) is None

    def test_missing_condition(self):
        assert _validate_filter({}) is not None

    def test_condition_without_type(self):
        assert _validate_filter({"condition": {}}) is not None

    def test_not_a_dict(self):
        assert _validate_filter("nope") is not None
