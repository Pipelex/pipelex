"""`POST /v1/resolve-storage-url/bulk` and `GET /v1/storage/{key}`: a self-hosted runner hands back what it stores.

A run's long texts, the images it generates and the files it receives travel as `pipelex-storage://` references into
this runner's storage. Every client reads one back the same way: it sends the references to the bulk resolve route,
receives one short-lived link per reference, and fetches each link without its credential. On the hosted plane the
platform serves that route, since it alone knows the organization that owns an object; a self-hosted runner, with no
platform in front of it, serves the same contract for its own storage, field for field, so neither SDK, nor any client
built on them, has to know which kind of server it talks to.

**A caller resolves what its runs may read when they name no read scope** (`caller_read_scope`, the rule the run
routes follow). Under `AUTH_MODE=jwt` that is its own `user_id`, and a reference under another scope is refused on its
item, as the platform refuses another organization's. A deployment that identifies no caller (`AUTH_MODE=none`, or the
shared `api_key`) has one tenant, whose runs may already write and read any key through `storage_scope` and
`read_scope`, so it resolves any reference that parses. A reference that does not parse is refused on its item as
`pipelex.storage.uri_invalid`; the request answers `200` whenever every reference got a verdict.

**A resolved link is this runner's own signed download route** (`pipelex_api.storage_links`), mounted outside the
authenticated router like `PUT /v1/blobs/{sha256}`: its signed query authorizes it, so a browser can display an image
from it directly.

**Neither route is mounted when the runner trusts forwarded identity** (`trusts_forwarded_identity`). Such a runner
sits behind a host that owns tenancy, the hosted plane, whose edge sends `/v1/resolve-storage-url*` to its platform:
the forwarded id is a user, not the organization that owns the object, which is why the route left the runner there.
Not mounting it keeps a misrouted request from reaching a reader that cannot check organizations.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from mthds.protocol.problem.registry import CoreCode
from pipelex import log
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.problem import make_problem_item
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.storage_scope import is_key_within_read_scope
from pipelex.tools.misc.filetype_utils import mime_type_of_file_name
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageKind
from pydantic import BaseModel, ConfigDict, Field

from pipelex_api.exceptions import RunnerAuthError, StoredObjectMissingError
from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.openapi_responses import COMMON_PROBLEM_RESPONSES, PROBLEM_403_STORAGE_LINK, PROBLEM_404_STORAGE_OBJECT, PROBLEM_422, PROBLEM_500
from pipelex_api.routes.pipelex.pipeline import READ_SCOPE_UNDER_CALLER_REQUIREMENT, caller_read_scope
from pipelex_api.security import trusts_forwarded_identity
from pipelex_api.storage_links import (
    DOWNLOAD_ROUTE_NAME,
    EXPIRES_PARAM,
    SIGNATURE_PARAM,
    download_link,
    is_download_authorized,
    storage_key_of,
)

resolve_router = APIRouter(tags=["storage"], route_class=JsonBodyRoute)
download_router = APIRouter(tags=["storage"])

# The bounds of the platform's bulk resolve route, which a client chunks its references by: one reference, as a request
# field, and how many references one request holds. Contract numbers, the same on every server serving the route.
STORAGE_URI_MAX_CHARS = 512
MAX_BULK_RESOLVE_URIS = 100

# What a download refused for its link lacks, as the `requirement` of its `auth.forbidden`.
SIGNED_STORAGE_LINK_REQUIREMENT = "signed_storage_link"
_PDF_MEDIA_TYPE = "application/pdf"
_OCTET_STREAM = "application/octet-stream"
# The characters of an HTTP token (RFC 7230 `tchar`), which the type and the subtype of a media type are each made of.
_TOKEN_CHARS = frozenset("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


class BulkResolveStorageUrlRequest(BaseModel):
    """The references to resolve, the platform's request field for field."""

    model_config = ConfigDict(extra="forbid")

    uris: list[Annotated[str, Field(max_length=STORAGE_URI_MAX_CHARS)]] = Field(
        ...,
        max_length=MAX_BULK_RESOLVE_URIS,
        description=f"pipelex-storage:// URIs to resolve, at most {MAX_BULK_RESOLVE_URIS} per request",
    )


class RefusalItem(BaseModel):
    """Why one reference was refused, as a value inside a `200`: the problem item of the refusal, the platform's field for field.

    `code` is the registry code the refusal carries, so a client that maps those codes applies the same mapping per
    reference, `detail` the code's sentence, and `params` the parameters the code declares.
    """

    code: str = Field(description="The registry code the refusal of this reference carries")
    detail: str = Field(description="The code's sentence for this reference")
    params: dict[str, Any] | None = Field(default=None, description="The parameters the code declares; null when it declares none")


class BulkResolveStorageUrlItem(BaseModel):
    """One verdict per reference. A client branches on `error`, never on the HTTP status.

    Either `url` and `expires_at` are set and `error` is null, or `error` is set and the three link fields are null.
    """

    uri: str = Field(..., description="The reference exactly as sent")
    url: str | None = Field(default=None, description="Short-lived signed download URL on this runner; null when the reference was refused")
    expires_at: datetime | None = Field(default=None, description="UTC expiry of the signed URL; null when refused")
    content_type: str | None = Field(default=None, description="Content type guessed from the URI extension; null when unknown or refused")
    error: RefusalItem | None = Field(
        default=None,
        description=(
            "Why the reference was refused: `pipelex.storage.uri_invalid` for a reference that does not parse, or "
            "`auth.forbidden` whose `requirement` is `read_scope_under_caller` for one outside the caller's scope; null when resolved"
        ),
    )


class BulkResolveStorageUrlResponse(BaseModel):
    items: list[BulkResolveStorageUrlItem] = Field(..., description="One item per requested reference, in the request's order")


def _refusal(*, code: ErrorCode, params: dict[str, Any] | None = None) -> RefusalItem:
    item = make_problem_item(code=code, params=params)
    return RefusalItem(
        code=item.code, detail=item.detail, params=item.params.model_dump(mode="json", exclude_none=True) if item.params is not None else None
    )


@resolve_router.post(
    "/resolve-storage-url/bulk",
    response_model=BulkResolveStorageUrlResponse,
    summary="Resolve pipelex-storage:// references to short-lived download links, one verdict per reference.",
)
async def resolve_storage_urls_in_bulk(request: Request, request_data: BulkResolveStorageUrlRequest) -> JSONResponse:
    """Turn a list of `pipelex-storage://` URIs into short-lived download links, one verdict per reference (Pipelex API extension).

    The hosted platform's contract, for this runner's own storage. Under `AUTH_MODE=jwt` a reference resolves only when
    its key lies under the caller's `user_id`, and one under another scope is refused on its item as `auth.forbidden`
    whose `requirement` is `read_scope_under_caller`; a deployment that identifies no caller resolves any reference
    that parses. A reference that does not parse is refused on its item as `pipelex.storage.uri_invalid`; the request is a `200`
    because a verdict was produced for every reference. Resolving checks no file is stored at the address, as a
    presigned URL does not. Each link is this runner's own `GET /v1/storage/{key}`, at `PUBLIC_BASE_URL` when the
    deployment sets it, signed for that key and valid for `STORAGE_LINK_TTL_SECONDS`. More than
    `MAX_BULK_RESOLVE_URIS` references, or a reference past `STORAGE_URI_MAX_CHARS`, is a `422 request.invalid`.
    Not served when the runner trusts forwarded identity, where the host's platform serves it.
    """
    scope = caller_read_scope(request)
    items: list[BulkResolveStorageUrlItem] = []
    refused_outside_scope = 0
    for uri in request_data.uris:
        key = storage_key_of(uri=uri)
        if key is None:
            items.append(BulkResolveStorageUrlItem(uri=uri, error=_refusal(code=PipelexErrorCode.STORAGE_URI_INVALID)))
            continue
        if scope is not None and not is_key_within_read_scope(key=key, read_scope=scope):
            refused_outside_scope += 1
            refusal = _refusal(code=CoreCode.AUTH_FORBIDDEN, params={"requirement": READ_SCOPE_UNDER_CALLER_REQUIREMENT})
            items.append(BulkResolveStorageUrlItem(uri=uri, error=refusal))
            continue
        url, expires_at = download_link(request=request, key=key)
        items.append(BulkResolveStorageUrlItem(uri=uri, url=url, expires_at=expires_at, content_type=mime_type_of_file_name(file_name=key)))
    if refused_outside_scope:
        # On the single route of old such a refusal was a logged 403; here it is a value on a 200, so without this line a
        # caller probing another scope's references would leave no trace in the logs.
        log.warning(
            "Storage references outside the caller's scope were refused",
            fields={"storage.refused_count": refused_outside_scope, "storage.requested_count": len(request_data.uris)},
        )
    response = BulkResolveStorageUrlResponse(items=items)
    return JSONResponse(content=response.model_dump(mode="json", serialize_as_any=True, by_alias=True))


@download_router.get(
    "/storage/{key:path}",
    name=DOWNLOAD_ROUTE_NAME,
    response_class=Response,
    summary="Download one stored object from the signed link POST /resolve-storage-url/bulk resolved it to.",
    # Mounted outside the composite `/v1` router, so it inherits none of its shared problem responses: it declares the
    # statuses it can produce itself, and never answers 401.
    responses={
        200: {
            "description": "The object's bytes, under the bare media type the route derives from the stored type and the key's name.",
            "content": {_OCTET_STREAM: {"schema": {"type": "string", "format": "binary"}}},
        },
        403: PROBLEM_403_STORAGE_LINK,
        404: PROBLEM_404_STORAGE_OBJECT,
        422: PROBLEM_422,
        500: PROBLEM_500,
    },
)
async def get_stored_object(
    key: Annotated[str, Path(description="The object's storage key: its pipelex-storage:// reference without the scheme.")],
    expires: Annotated[str | None, Query(alias=EXPIRES_PARAM, description="When the link expires, in seconds since the epoch.")] = None,
    signature: Annotated[str | None, Query(alias=SIGNATURE_PARAM, description="The link's signature.")] = None,
) -> Response:
    """Answer one stored object's bytes, as the link `POST /v1/resolve-storage-url/bulk` resolved it to (Pipelex API extension).

    The link's signed query is its authorization, so the route needs no bearer token. A link whose signature does not
    hold, or that has expired, is a 403 `auth.forbidden` whose `requirement` is `signed_storage_link`, as is a query
    that is not one this runner signs; a link whose address holds no file, or one the storage provider refuses as an
    address, a 404 `pipelex.storage.object_missing`. The bytes come from the runner's configured storage provider,
    under the bare media type `served_media_type` derives; the answer is sandboxed, so a stored HTML page never runs a
    script on the runner's origin, except a PDF, which a sandbox keeps a browser's own viewer from displaying.
    """
    if storage_key_of(uri=f"{PIPELEX_STORAGE_SCHEME}{key}") is None or not is_download_authorized(key=key, expires=expires, signature=signature):
        msg = (
            "This download carries no valid link: resolve the reference with POST /v1/resolve-storage-url/bulk, and fetch the link before it expires."
        )
        raise RunnerAuthError(msg).with_error_code(CoreCode.AUTH_FORBIDDEN).with_params(requirement=SIGNED_STORAGE_LINK_REQUIREMENT)
    provider = get_storage_provider()
    try:
        stored = await provider.load_with_metadata(f"{PIPELEX_STORAGE_SCHEME}{key}")
    except StorageFileNotFoundError as exc:
        msg = "The link's signature holds, but the runner's storage holds no file at the address it names."
        raise StoredObjectMissingError(msg) from exc
    except StorageInvalidUriError as exc:
        # A key the provider refuses as an address names no stored file, which is all this link's holder needs to know.
        msg = "The link's signature holds, but the runner's storage refuses the address it names as holding no stored file."
        raise StoredObjectMissingError(msg) from exc
    media_type = served_media_type(key=key, provider_type=stored.mime_type, storage_kind=provider.storage_kind)
    return Response(content=stored.data, media_type=media_type, headers=_download_headers(media_type=media_type))


def bare_media_type(*, content_type: str | None) -> str | None:
    """The bare `type/subtype` a content type names, lowercase, or None when it names no well-formed one.

    The parameters after a `;` are dropped. What is left must be one type and one subtype, each a non-empty HTTP token
    (RFC 7230 `tchar`), joined by exactly one `/`; a content type holding a comma anywhere, or any other shape, names
    none, so the route never serves a type it has not validated.
    """
    if content_type is None or "," in content_type:
        return None
    essence = content_type.split(";", 1)[0].strip()
    media_type, slash, subtype = essence.partition("/")
    if not slash or not media_type or not subtype:
        return None
    if any(char not in _TOKEN_CHARS for char in media_type) or any(char not in _TOKEN_CHARS for char in subtype):
        return None
    return essence.lower()


def _keeps_stored_type(*, storage_kind: StorageKind) -> bool:
    """Whether a provider of this kind answers the content type an object was stored with, rather than one it guessed.

    S3 and GCS keep the type a write gave them, and a plugin is taken at its word. The local and in-memory providers keep
    none: the type they answer is sniffed from the bytes, which the name the object was stored under says better.
    """
    match storage_kind:
        case "s3" | "gcs" | "plugin":
            return True
        case "local" | "memory":
            return False


def served_media_type(*, key: str, provider_type: str | None, storage_kind: StorageKind) -> str:
    """The bare media type the download route serves an object under, which agrees with what was stored.

    Both candidates are reduced to a validated bare type first (`bare_media_type`): the type the provider answered and
    the one the key's name implies, which is the type the resolve route reported. A provider that keeps the type an
    object was stored with has its type served, else the name's; one that keeps none has the name's type served, else
    the one it sniffed from the bytes. With neither, the object is served as `application/octet-stream`.
    """
    stored_type = bare_media_type(content_type=provider_type)
    name_type = bare_media_type(content_type=mime_type_of_file_name(file_name=key))
    if _keeps_stored_type(storage_kind=storage_kind):
        return stored_type or name_type or _OCTET_STREAM
    return name_type or stored_type or _OCTET_STREAM


def _download_headers(*, media_type: str) -> dict[str, str]:
    """The headers of a download: never sniffed, kept private, and sandboxed unless the object is a PDF.

    `media_type` is the bare type `served_media_type` derived. A sandboxed answer runs no script on the runner's origin,
    which a stored HTML page or SVG image would otherwise run. A PDF is the exception, since Chromium's viewer refuses to
    display a document served under a sandbox (crbug 413851), and a PDF runs no script on the origin that serves it.
    """
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private"}
    if media_type != _PDF_MEDIA_TYPE:
        headers["Content-Security-Policy"] = "sandbox"
    return headers


def mount_storage_routes(*, app: FastAPI, auth_dependency: Any) -> None:
    """Mount the resolve route behind the deployment's authentication and the download route without it, unless the
    runner trusts forwarded identity, where neither is mounted.
    """
    if trusts_forwarded_identity():
        return
    app.include_router(download_router, prefix="/v1")
    app.include_router(resolve_router, prefix="/v1", dependencies=[Depends(auth_dependency)], responses=COMMON_PROBLEM_RESPONSES)
