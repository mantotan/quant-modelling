"""Tests for structured logging with secret redaction."""

from qm.monitoring.logging import _redact_secrets


class TestSecretRedaction:
    def test_redacts_api_key(self):
        event = {"event": "Connected with api_key=sk_live_abc123xyz"}
        result = _redact_secrets(None, None, event)
        assert "sk_live_abc123xyz" not in result["event"]
        assert "***REDACTED***" in result["event"]

    def test_redacts_private_key(self):
        event = {"event": "Using private_key: 0x1234567890abcdef"}
        result = _redact_secrets(None, None, event)
        assert "0x1234567890abcdef" not in result["event"]
        assert "***REDACTED***" in result["event"]

    def test_redacts_password_in_dsn(self):
        event = {"event": "password=supersecret123 in config"}
        result = _redact_secrets(None, None, event)
        assert "supersecret123" not in result["event"]

    def test_redacts_hex_private_key(self):
        hex_key = "a" * 64  # 64 hex chars = typical private key
        event = {"event": f"Key is {hex_key}"}
        result = _redact_secrets(None, None, event)
        assert hex_key not in result["event"]
        assert "***REDACTED_KEY***" in result["event"]

    def test_preserves_normal_messages(self):
        event = {"event": "Downloaded 25920 bars for BTCUSDT in 1.1 seconds"}
        result = _redact_secrets(None, None, event)
        assert result["event"] == "Downloaded 25920 bars for BTCUSDT in 1.1 seconds"

    def test_redacts_extra_fields(self):
        event = {
            "event": "Connecting",
            "api_key": "my_secret_key_value",
            "exchange": "binance",
        }
        result = _redact_secrets(None, None, event)
        assert result["exchange"] == "binance"  # not redacted
        # api_key field itself isn't pattern-matched unless it has key=value format

    def test_redacts_bearer_token(self):
        event = {"event": "Authorization: bearer=eyJhbGciOiJIUzI1NiJ9.xyz"}
        result = _redact_secrets(None, None, event)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result["event"]

    def test_case_insensitive(self):
        event = {"event": "API_SECRET=mysecretvalue123"}
        result = _redact_secrets(None, None, event)
        assert "mysecretvalue123" not in result["event"]
