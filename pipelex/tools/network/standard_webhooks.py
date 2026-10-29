"""The signature of a call in the Standard Webhooks v1 format, the form a caller's webhook is signed in.

Standard Webhooks (https://www.standardwebhooks.com/) signs the content ``{webhook-id}.{webhook-timestamp}.{body}``
with HMAC-SHA256 under the key a ``whsec_`` secret carries, the standard base64 of its bytes after the prefix, and writes
each signature as ``v1,`` followed by the standard base64 of the MAC, with its padding. While several secrets are live,
the ``webhook-signature`` header carries one signature per secret, separated by single spaces, the current secret's
first. A receiver verifies the call with any Standard Webhooks library.

The functions here read no configuration and send nothing: the delivery that signs a call decides which secrets are
live and which bytes it sends, and signs exactly those bytes.
"""

import base64
import binascii
import hashlib
import hmac
from collections.abc import Sequence

WEBHOOK_SECRET_PREFIX = "whsec_"
"""The prefix of a Standard Webhooks signing secret, ahead of the standard base64 of its key."""

SIGNATURE_VERSION = "v1"
"""The version of the symmetric signature, the one this module writes."""


def decode_webhook_secret(*, secret: str) -> bytes:
    """The key a ``whsec_`` secret carries: the standard base64 after its prefix, decoded.

    Args:
        secret: The secret, as its operator configured it.

    Returns:
        The key's bytes.

    Raises:
        ValueError: The secret does not start with ``whsec_``, or what follows is not standard base64 of at least one byte.
    """
    if not secret.startswith(WEBHOOK_SECRET_PREFIX):
        msg = f"A webhook signing secret starts with '{WEBHOOK_SECRET_PREFIX}'."
        raise ValueError(msg)
    encoded_key = secret.removeprefix(WEBHOOK_SECRET_PREFIX)
    try:
        key = base64.b64decode(encoded_key, validate=True)
    except binascii.Error as exc:
        msg = f"A webhook signing secret holds standard base64 after '{WEBHOOK_SECRET_PREFIX}'."
        raise ValueError(msg) from exc
    if not key:
        msg = f"A webhook signing secret holds a key after '{WEBHOOK_SECRET_PREFIX}'."
        raise ValueError(msg)
    return key


def sign_webhook(*, secret_keys: Sequence[bytes], webhook_id: str, webhook_timestamp: str, body: bytes) -> str:
    """The ``webhook-signature`` header of a call: one ``v1,`` signature per live secret, separated by single spaces.

    Args:
        secret_keys: The keys of the live secrets, the current secret's first; at least one.
        webhook_id: The call's ``webhook-id`` header, exactly as it is sent.
        webhook_timestamp: The call's ``webhook-timestamp`` header, exactly as it is sent.
        body: The body's bytes, exactly as they are sent.

    Returns:
        The header's value.

    Raises:
        ValueError: No key was given.
    """
    if not secret_keys:
        msg = "A webhook is signed under at least one secret."
        raise ValueError(msg)
    signed_content = f"{webhook_id}.{webhook_timestamp}.".encode() + body
    signatures: list[str] = []
    for secret_key in secret_keys:
        mac = hmac.new(secret_key, signed_content, hashlib.sha256).digest()
        signatures.append(f"{SIGNATURE_VERSION},{base64.b64encode(mac).decode('ascii')}")
    return " ".join(signatures)
