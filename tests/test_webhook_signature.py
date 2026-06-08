"""Tests for webhook signature verification.

Imports webhook module under controlled env vars so the module-level
os.environ lookups don't fail.
"""
import hashlib
import hmac
import importlib
import os
import sys


def _import_webhook():
    """(Re)import webhook with required env vars set."""
    os.environ.setdefault("GITHUB_TOKEN", "test-token")
    os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")
    os.environ.setdefault("TARGET_DIR", "/tmp")
    # Force a fresh import each time to pick up env changes if needed
    if "webhook" in sys.modules:
        return importlib.reload(sys.modules["webhook"])
    return importlib.import_module("webhook")


def _sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), msg=payload, digestmod=hashlib.sha256).hexdigest()


class TestIsValidSignature:
    def test_valid_signature(self):
        webhook = _import_webhook()
        payload = b'{"action": "created"}'
        sig = _sign("test-secret", payload)
        assert webhook.is_valid_signature(payload, sig) is True

    def test_wrong_signature(self):
        webhook = _import_webhook()
        payload = b'{"action": "created"}'
        bad_sig = _sign("wrong-secret", payload)
        assert webhook.is_valid_signature(payload, bad_sig) is False

    def test_missing_prefix(self):
        webhook = _import_webhook()
        payload = b'{}'
        digest = hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
        # No "sha256=" prefix
        assert webhook.is_valid_signature(payload, digest) is False

    def test_empty_signature(self):
        webhook = _import_webhook()
        assert webhook.is_valid_signature(b"payload", "") is False

    def test_payload_tampered(self):
        webhook = _import_webhook()
        original = b'{"a": 1}'
        sig = _sign("test-secret", original)
        tampered = b'{"a": 2}'
        assert webhook.is_valid_signature(tampered, sig) is False
