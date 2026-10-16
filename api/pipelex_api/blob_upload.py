"""The signed upload targets `POST /v1/blobs/missing` names, and their check on `PUT /v1/blobs/{sha256}`.

A sender uploads a blob to the target the runner named, carrying exactly the headers it named, so the target itself
must say that the upload is allowed, as a presigned URL does on an object store. This runner signs each target it
names: its URL is its own `PUT /v1/blobs/{sha256}` with a query naming the blob store's scope, an expiry and an
HMAC-SHA256 signature over the scope, the hash and the expiry. The upload route checks the signature and the expiry,
writes under the scope the signature binds and nowhere else, and answers a missing, forged or expired signature with a
403 `BlobUploadNotAuthorized`. The upload route therefore needs no bearer token: only a caller who passed the
deployment's authentication on `POST /v1/blobs/missing` holds a target, for one hash, in its own scope, for a while.

The key is `BLOB_UPLOAD_SIGNING_KEY` when the deployment sets it, which it must when several instances serve one
deployment, since a target named by one instance is checked by whichever instance receives the upload; otherwise each
process draws a random key of its own at its first signature.
"""

import hashlib
import hmac
import secrets
import time
from functools import cache
from urllib.parse import urlencode

from pipelex.system.environment import get_optional_env

from pipelex_api.limits import BLOB_UPLOAD_URL_TTL_SECONDS

SCOPE_PARAM = "scope"
EXPIRES_PARAM = "expires"
SIGNATURE_PARAM = "signature"


@cache
def _signing_key() -> bytes:
    configured = get_optional_env("BLOB_UPLOAD_SIGNING_KEY")
    if configured:
        return configured.encode("utf-8")
    return secrets.token_bytes(32)


def _signature(*, scope: str, sha256: str, expires: int) -> str:
    message = f"{scope}\n{sha256}\n{expires}".encode()
    return hmac.new(_signing_key(), message, hashlib.sha256).hexdigest()


def signed_upload_query(*, scope: str, sha256: str) -> str:
    """The query string of an upload target for one blob in one scope, valid for `BLOB_UPLOAD_URL_TTL_SECONDS`."""
    expires = int(time.time()) + BLOB_UPLOAD_URL_TTL_SECONDS
    return urlencode({SCOPE_PARAM: scope, EXPIRES_PARAM: expires, SIGNATURE_PARAM: _signature(scope=scope, sha256=sha256, expires=expires)})


def is_upload_authorized(*, scope: str | None, sha256: str, expires: int | None, signature: str | None) -> bool:
    """Whether an upload carries a signature this runner made for this hash and scope, still within its expiry."""
    if scope is None or expires is None or signature is None:
        return False
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(_signature(scope=scope, sha256=sha256, expires=expires), signature)
