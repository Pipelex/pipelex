"""The signed upload targets `POST /v1/blobs/missing` names, and their check on `PUT /v1/blobs/{sha256}`.

A sender uploads a blob to the target the runner named, carrying exactly the headers it named, so the target itself
must say that the upload is allowed, as a presigned URL does on an object store. This runner signs each target it
names: its URL is its own `PUT /v1/blobs/{sha256}` with a query naming the blob store's scope, an expiry and an
HMAC-SHA256 signature over the scope, the hash and the expiry. The upload route checks the signature and the expiry,
writes under the scope the signature binds and nowhere else, and answers a missing, forged or expired signature with a
403 `auth.forbidden` whose `requirement` is a signed upload target. The upload route therefore needs no bearer token:
only a caller who passed the deployment's authentication on `POST /v1/blobs/missing` holds a target, for one hash, in
its own scope, for a while.

The signing key and the address a target starts with are those of every link this runner signs
(`pipelex_api.signed_links`): `LINK_SIGNING_KEY`, which a deployment of several instances must set, and
`PUBLIC_BASE_URL`, else the URL of the request that asked for the target.
"""

import time
from urllib.parse import urlencode

from fastapi import Request

from pipelex_api.limits import BLOB_UPLOAD_URL_TTL_SECONDS
from pipelex_api.signed_links import LinkPurpose, is_expiry_valid, is_signature_valid, link_signature, public_route_url

_UPLOAD_ROUTE_NAME = "put_blob"

SCOPE_PARAM = "scope"
EXPIRES_PARAM = "expires"
SIGNATURE_PARAM = "signature"


def _signed_message(*, scope: str, sha256: str, expires: int) -> str:
    return f"{scope}\n{sha256}\n{expires}"


def signed_upload_query(*, scope: str, sha256: str) -> str:
    """The query string of an upload target for one blob in one scope, valid for `BLOB_UPLOAD_URL_TTL_SECONDS`."""
    expires = int(time.time()) + BLOB_UPLOAD_URL_TTL_SECONDS
    signature = link_signature(purpose=LinkPurpose.BLOB_UPLOAD, message=_signed_message(scope=scope, sha256=sha256, expires=expires))
    return urlencode({SCOPE_PARAM: scope, EXPIRES_PARAM: expires, SIGNATURE_PARAM: signature})


def upload_target_url(*, request: Request, scope: str, sha256: str) -> str:
    """The signed URL a sender uploads one blob to: this runner's `PUT /v1/blobs/{sha256}`, at its public address."""
    query = signed_upload_query(scope=scope, sha256=sha256)
    return public_route_url(request=request, route_name=_UPLOAD_ROUTE_NAME, query=query, sha256=sha256)


def is_upload_authorized(*, scope: str | None, sha256: str, expires: str | None, signature: str | None) -> bool:
    """Whether an upload carries a signature this runner made for this hash and scope, still within its expiry.

    Every part of the query is the caller's text, read as such: an expiry that is not a decimal integer, or a signature
    holding characters no signature this runner makes holds, is no valid target, never a failure of the check.
    """
    if scope is None or expires is None or signature is None:
        return False
    if not is_expiry_valid(expires=expires, now=int(time.time())):
        return False
    message = _signed_message(scope=scope, sha256=sha256, expires=int(expires))
    return is_signature_valid(purpose=LinkPurpose.BLOB_UPLOAD, message=message, signature=signature)
