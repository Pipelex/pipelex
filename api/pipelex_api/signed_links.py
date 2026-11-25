"""The links this runner signs, and the address it hands them out at.

The runner hands out two kinds of link that carry their own authorization in a signed query, as a presigned URL on an
object store does: the upload targets `POST /v1/blobs/missing` names (`pipelex_api.blob_upload`), and the download links
`POST /v1/resolve-storage-url/bulk` resolves a stored reference to (`pipelex_api.storage_links`). Both are signed with
one key, each under a purpose of its own, so a signature made for one kind of link never holds for the other.

The key is `LINK_SIGNING_KEY` when the deployment sets it, which it must when several instances serve one deployment,
since a link one instance signed is checked by whichever instance receives it; otherwise each process draws a random key
of its own at its first signature, so its links stop holding when it restarts.

A link starts with `PUBLIC_BASE_URL` when the deployment sets it, the address its clients reach the API at, such as
`https://runner.example.com`: behind a proxy that terminates TLS or serves the API under a path prefix, the URL the
runner received a request at is not the one a client can reach. Unset, a link starts with the URL of the request that
asked for it.
"""

import hashlib
import hmac
import secrets
from enum import StrEnum
from functools import cache
from urllib.parse import urlsplit

from fastapi import Request
from pipelex.system.environment import get_optional_env

from pipelex_api.exceptions import RunnerMisconfiguredError

LINK_SIGNING_KEY_ENV = "LINK_SIGNING_KEY"
PUBLIC_BASE_URL_ENV = "PUBLIC_BASE_URL"


class LinkPurpose(StrEnum):
    """What a signed link authorizes, which keys its signature apart from every other kind of link's."""

    BLOB_UPLOAD = "blob_upload"
    STORAGE_DOWNLOAD = "storage_download"


@cache
def _signing_key() -> bytes:
    configured = get_optional_env(LINK_SIGNING_KEY_ENV)
    if configured:
        return configured.encode("utf-8")
    return secrets.token_bytes(32)


def _purpose_key(*, purpose: LinkPurpose) -> bytes:
    """The key one kind of link is signed with, derived from the deployment's key and the purpose."""
    return hmac.new(_signing_key(), f"pipelex-api link {purpose}".encode(), hashlib.sha256).digest()


def link_signature(*, purpose: LinkPurpose, message: str) -> str:
    """The HMAC-SHA256 signature, in lowercase hexadecimal, of what a link of this purpose binds."""
    return hmac.new(_purpose_key(purpose=purpose), message.encode("utf-8"), hashlib.sha256).hexdigest()


def is_signature_valid(*, purpose: LinkPurpose, message: str, signature: str) -> bool:
    """Whether `signature`, the caller's text, is the one this runner makes for this message and purpose."""
    # Compared as bytes: `compare_digest` refuses text holding a character outside ASCII, which a forged signature may.
    expected = link_signature(purpose=purpose, message=message).encode("ascii")
    return hmac.compare_digest(expected, signature.encode("utf-8", "surrogatepass"))


def is_expiry_valid(*, expires: str, now: int) -> bool:
    """Whether `expires`, the caller's text, is a decimal number of seconds since the epoch not yet past."""
    if not expires.isascii() or not expires.isdecimal():
        return False
    return int(expires) >= now


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


def public_route_url(*, request: Request, route_name: str, query: str, **path_params: str) -> str:
    """The absolute URL of one of this runner's routes with a query, at the runner's public address.

    The path parameters are written into the path as they are given, so a caller passes them already percent-encoded.
    """
    base_url = _public_base_url()
    if base_url is None:
        return f"{request.url_for(route_name, **path_params)}?{query}"
    return f"{base_url}{request.app.url_path_for(route_name, **path_params)}?{query}"
