import hashlib
import hmac

from src.core.logic.slack_security import verify_slack_signature


def test_verify_slack_signature_accepts_valid_hmac():
    secret = "test-signing-secret"
    timestamp = "1531420618"
    body = '{"type":"event_callback","event":{"type":"message","text":"hello team"}}'

    sig_basestring = f"v0:{timestamp}:{body}"
    signature = "v0=" + hmac.new(
        secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    assert verify_slack_signature(secret, timestamp, body, signature) is True


def test_verify_slack_signature_rejects_tampered_body():
    secret = "test-signing-secret"
    timestamp = "1531420618"
    body = '{"type":"event_callback"}'
    wrong_signature = "v0=deadbeef"

    assert verify_slack_signature(secret, timestamp, body, wrong_signature) is False


def test_verify_slack_signature_rejects_missing_headers():
    assert verify_slack_signature("secret", "", "{}", "v0=abc") is False
    assert verify_slack_signature("secret", "123", "{}", "") is False
