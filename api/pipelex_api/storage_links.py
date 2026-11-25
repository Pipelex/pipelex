"""The download links `POST /v1/resolve-storage-url/bulk` resolves a stored reference to, and their check.

A run's long texts, the images it generates and the files it receives are stored in this runner's storage and handed
back as `pipelex-storage://` references. A client turns one back into bytes by resolving it to a short-lived link and
fetching that link without its credential, as it does on the hosted platform, where the link is a presigned object-store
URL. Here the link is this runner's own `GET /v1/storage/{key}`, with a query holding an expiry and an HMAC-SHA256
signature over the key and the expiry, so the download route needs no bearer token: only a caller who passed the
deployment's authentication on the resolve route, for a reference under its own scope, holds a link, for a while.

The signing key and the address a link starts with are those of every link this runner signs
(`pipelex_api.signed_links`): `LINK_SIGNING_KEY`, which a deployment of several instances or worker processes must set, and
`PUBLIC_BASE_URL`, else the URL of the request that resolved the reference.
"""

import time
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from fastapi import Request
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

from pipelex_api.limits import STORAGE_LINK_TTL_SECONDS
from pipelex_api.signed_links import LinkPurpose, is_expiry_valid, is_signature_valid, link_signature, public_route_url

DOWNLOAD_ROUTE_NAME = "get_stored_object"

EXPIRES_PARAM = "expires"
SIGNATURE_PARAM = "signature"

# The fewest segments a stored object's key has: a scope and a file name.
_MIN_KEY_SEGMENTS = 2

# The longest name, in UTF-8 bytes, the filesystems a storage provider writes to hold for one path segment: a longer
# segment names no object any of them stores.
_MAX_SEGMENT_BYTES = 255


def storage_key_of(*, uri: str) -> str | None:
    """The storage key a `pipelex-storage://` reference names, or None when the reference does not parse.

    A reference parses when it starts with the scheme and its key has at least a scope and a file name, none of its
    segments empty, `.`, `..` or longer than 255 UTF-8 bytes, and no character in it a backslash, a control character
    or DEL: the local storage provider resolves a key against a directory, where any of those would name another file
    than the one the key reads as, or a name the filesystem cannot hold, and a key parsed so is safe in the path of a
    download link once each segment is percent-encoded.
    """
    if not uri.startswith(PIPELEX_STORAGE_SCHEME):
        return None
    key = uri.removeprefix(PIPELEX_STORAGE_SCHEME)
    if any(char == "\\" or ord(char) < 0x20 or ord(char) == 0x7F for char in key):
        return None
    segments = key.split("/")
    if len(segments) < _MIN_KEY_SEGMENTS:
        return None
    for segment in segments:
        if segment in {"", ".", ".."} or len(segment.encode("utf-8", "surrogatepass")) > _MAX_SEGMENT_BYTES:
            return None
    return key


def _signed_message(*, key: str, expires: int) -> str:
    return f"{key}\n{expires}"


def download_link(*, request: Request, key: str) -> tuple[str, datetime]:
    """The signed URL one stored object is downloaded from, at the runner's public address, and when it expires.

    Valid for `STORAGE_LINK_TTL_SECONDS`. The key is percent-encoded segment by segment in the link's path, and the
    route reads it back decoded, which is what the signature binds.
    """
    expires = int(time.time()) + STORAGE_LINK_TTL_SECONDS
    signature = link_signature(purpose=LinkPurpose.STORAGE_DOWNLOAD, message=_signed_message(key=key, expires=expires))
    query = urlencode({EXPIRES_PARAM: expires, SIGNATURE_PARAM: signature})
    url = public_route_url(request=request, route_name=DOWNLOAD_ROUTE_NAME, query=query, key=quote(key, safe="/"))
    return url, datetime.fromtimestamp(expires, tz=UTC)


def is_download_authorized(*, key: str, expires: str | None, signature: str | None) -> bool:
    """Whether a download carries a signature this runner made for this key, still within its expiry.

    Every part of the query is the caller's text, read as such: an expiry that is not a decimal integer, or a signature
    holding characters no signature this runner makes holds, is no valid link, never a failure of the check.
    """
    if expires is None or signature is None:
        return False
    if not is_expiry_valid(expires=expires, now=int(time.time())):
        return False
    message = _signed_message(key=key, expires=int(expires))
    return is_signature_valid(purpose=LinkPurpose.STORAGE_DOWNLOAD, message=message, signature=signature)
