import hashlib
import hmac


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
) -> bool:
    if not timestamp or not signature:
        return False
    sig_basestring = f"v0:{timestamp}:{body}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
