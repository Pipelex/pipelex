"""The signed upload targets `POST /v1/blobs/missing` names, and their check on `PUT /v1/blobs/{sha256}`.

A sender uploads a blob to the target the runner named, carrying exactly the headers it named, so the target itself
must say that the upload is allowed, as a presigned URL does on an object store. This runner signs each target it
names: its URL is its own `PUT /v1/blobs/{sha256}` with a query naming the blob store's scope, an expiry and an
HMAC-SHA256 signature over the scope, the hash and the expiry. The upload route checks the signature and the expiry,
writes under the scope the signature binds and nowhere else, and answers a missing, forged or expired signature with a
403 `auth.forbidden` whose `requirement` is a signed upload target. The upload route therefore needs no bearer token:
only a caller who passed the deployment's authentication on `POST /v1/blobs/missing` holds a target, for one hash, in
its own scope, for a while.

The key is `BLOB_UPLOAD_SIGNING_KEY` when the deployment sets it, which it must when several instances serve one
deployment, since a target named by one instance is checked by whichever instance receives the upload; otherwise each
process draws a random key of its own at its first signature.

A target's URL starts with `PUBLIC_BASE_URL` when the deployment sets it, the address its clients reach the API at,
such as `https://runner.example.com`: behind a proxy that terminates TLS or serves the API under a path prefix, the URL
the runner received a request at is not the one a client can upload to. Unset, the target starts with the URL of the
request that asked for it.
"""

import hashlib
import hmac
import secrets
import time
from functools import cache
from urllib.parse import urlencode, urlsplit

from fastapi import Request
from pipelex.system.environment import get_optional_env

from pipelex_api.exceptions import RunnerMisconfiguredError
from pipelex_api.limits import BLOB_UPLOAD_URL_TTL_SECONDS

PUBLIC_BASE_URL_ENV = "PUBLIC_BASE_URL"
_UPLOAD_ROUTE_NAME = "put_blob"

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


def _public_base_url() -> str | None:
    """`PUBLIC_BASE_URL` without its trailing slash, or None when unset.

    Raises (as a problem document): a 500 `runtime.misconfigured` naming `PUBLIC_BASE_URL`, for a value that is not an
    absolute http or https URL without a query or a fragment.
    """
    configured = get_optional_env(PUBLIC_BASE_URL_ENV)
    if not configured:
        return None
    parts = urlsplit(configured)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
        msg = f"Server configuration error: {PUBLIC_BASE_URL_ENV} must be an absolute http or https URL, such as https://runner.example.com."
        raise RunnerMisconfiguredError(msg, component=PUBLIC_BASE_URL_ENV)
    return configured.rstrip("/")


def upload_target_url(*, request: Request, scope: str, sha256: str) -> str:
    """The signed URL a sender uploads one blob to: this runner's `PUT /v1/blobs/{sha256}`, at its public address."""
    query = signed_upload_query(scope=scope, sha256=sha256)
    base_url = _public_base_url()
    if base_url is None:
        return f"{request.url_for(_UPLOAD_ROUTE_NAME, sha256=sha256)}?{query}"
    return f"{base_url}{request.app.url_path_for(_UPLOAD_ROUTE_NAME, sha256=sha256)}?{query}"


def is_upload_authorized(*, scope: str | None, sha256: str, expires: str | None, signature: str | None) -> bool:
    """Whether an upload carries a signature this runner made for this hash and scope, still within its expiry.

    Every part of the query is the caller's text, read as such: an expiry that is not a decimal integer, or a signature
    holding characters no signature this runner makes holds, is no valid target, never a failure of the check.
    """
    if scope is None or expires is None or signature is None:
        return False
    if not expires.isascii() or not expires.isdecimal():
        return False
    expires_at = int(expires)
    if expires_at < int(time.time()):
        return False
    # Compared as bytes: `compare_digest` refuses text holding a character outside ASCII, which a forged signature may.
    expected = _signature(scope=scope, sha256=sha256, expires=expires_at).encode("ascii")
    return hmac.compare_digest(expected, signature.encode("utf-8", "surrogatepass"))
