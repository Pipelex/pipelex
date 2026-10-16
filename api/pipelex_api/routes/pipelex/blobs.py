"""`POST /v1/blobs/missing`: which of a sender's blobs this runner lacks, and where to upload each (MTHDS Protocol).

A sender about to send a method by hash first asks which of its files' bytes this runner holds, then uploads only the
missing ones to the targets the answer names (`pipelex_api.routes.blob_upload`), then sends the request with hash
entries. The blobs live in the runner's blob store (`pipelex_api.blob_store`), under the caller's scope: the request's
`read_scope` query parameter when a multi-tenant host sends one for the organization it serves, else the caller's own
id, the scope a run's hash entries are resolved in.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from pipelex.system.storage_scope import validate_read_scope
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.blob_upload import upload_target_url
from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_validation_error
from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.method_tree_request import ensure_within_tree_limits
from pipelex_api.routes.pipelex.pipeline import resolve_blob_scope

router = APIRouter(tags=["blobs"], route_class=JsonBodyRoute)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
_OCTET_STREAM = "application/octet-stream"
_SIZE_DESCRIPTION = (
    "The length of the bytes, a JSON integer written without a fraction or an exponent. A size written 13.0 is refused, "
    "although JSON Schema's integer type admits it."
)


class BlobRef(BaseModel):
    """A blob, named by its SHA-256 in lowercase hexadecimal and its length in bytes."""

    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(pattern=SHA256_PATTERN, description="The SHA-256 of the bytes, in lowercase hexadecimal.")
    size: StrictInt = Field(ge=0, description=_SIZE_DESCRIPTION)


class MissingBlobsRequest(BaseModel):
    """The blobs a sender is about to send by hash, and optionally the tree they make up."""

    model_config = ConfigDict(extra="allow")

    blobs: list[BlobRef] = Field(description="The blobs to check, each hash listed once.")
    digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$", description="The tree digest of the method tree the blobs make up (optional)."
    )


class UploadTarget(BaseModel):
    """Where to upload one blob: send its bytes as the whole body of a request with this method to this URL, with exactly these headers."""

    method: str = Field(description="The HTTP method, such as PUT.")
    url: str = Field(description="Where to send the bytes: this runner's own `PUT /v1/blobs/{sha256}`, with a signed query.")
    headers: dict[str, str] = Field(description="The headers to send, exactly.")


class MissingBlob(BaseModel):
    """A blob the runner lacks, with where to upload it."""

    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(ge=0, description=_SIZE_DESCRIPTION)
    upload: UploadTarget


class MissingBlobsResult(BaseModel):
    """The blobs of the request the runner does not hold."""

    missing: list[MissingBlob]


def _unique_blobs(*, blobs: list[BlobRef]) -> dict[str, int]:
    """Each hash of the request once, with its size; a hash given twice with different sizes is a 422."""
    sizes: dict[str, int] = {}
    for blob in blobs:
        known = sizes.get(blob.sha256)
        if known is not None and known != blob.size:
            msg = f"The blob {blob.sha256} is listed twice with different sizes, {known} and {blob.size}: one hash names one set of bytes."
            raise_validation_error(message=msg, error_type=ErrorType.BLOB_MISMATCH)
        sizes[blob.sha256] = blob.size
    return sizes


@router.post(
    "/blobs/missing",
    summary="Which of these blobs the runner lacks, and where to upload each.",
    openapi_extra={"x-mthds-protocol": True},
)
async def find_missing_blobs(
    request: Request,
    request_data: MissingBlobsRequest,
    read_scope: Annotated[
        str | None,
        Query(
            description=(
                "PIPELEX-API EXTENSION — the blob store's scope, as a run's `read_scope`: a multi-tenant host sends the one "
                "of the organization it serves. Omit it and the caller's own id is the scope."
            )
        ),
    ] = None,
) -> MissingBlobsResult:
    """List every blob of the request this runner does not hold, each with a signed upload target (MTHDS Protocol).

    A blob it holds at the stated size is left out, and an empty list means there is nothing to upload; a hash held
    at another size than the one stated is listed too, and its upload tells the two cases apart: bytes of the size held
    change nothing, and bytes of another size mean the object held is damaged, a 500 `BlobStoreCorrupted`, since nothing
    writes over a blob. When the request names the tree the blobs
    make up by its `digest`, this runner has recorded that tree as held in full, which it does only after reading every
    file of a tree a request sent, and every listed blob is a file of that tree, the answer is an empty list at once.
    A hash given twice with different sizes is a 422 `BlobMismatch`, and a blob or a set of blobs past this runner's
    tree limits a 422 `MethodTreeTooLarge`, both refused before anything is uploaded. Each upload target is this runner's own
    `PUT /v1/blobs/{sha256}`, at `PUBLIC_BASE_URL` when the deployment sets it, its query signed for that hash and
    the caller's scope, valid for `BLOB_UPLOAD_URL_TTL_SECONDS`, to send with exactly the headers it names.
    """
    if read_scope is not None:
        try:
            validate_read_scope(value=read_scope)
        except ValueError as exc:
            raise_validation_error(message=str(exc), error_type=ErrorType.INVALID_READ_SCOPE)
    sizes = _unique_blobs(blobs=request_data.blobs)
    largest_sha256 = max(sizes, key=lambda sha256: sizes[sha256], default=None)
    ensure_within_tree_limits(
        file_count=len(sizes),
        total_bytes=sum(sizes.values()),
        largest_path=largest_sha256,
        largest_bytes=sizes[largest_sha256] if largest_sha256 is not None else 0,
        label="The blobs of this request",
    )
    scope = resolve_blob_scope(request, read_scope=read_scope)
    blob_store = RunnerBlobStore.make_for_scope(scope=scope)
    if request_data.digest is not None:
        tree_hashes = await blob_store.tree_hashes(tree_digest=request_data.digest)
        # The digest answers alone only for blobs that are files of the tree it names, which this runner holds in full.
        if tree_hashes is not None and tree_hashes.issuperset(sizes):
            return MissingBlobsResult(missing=[])
    missing: list[MissingBlob] = []
    for sha256 in await blob_store.missing_blobs(sizes=sizes):
        url = upload_target_url(request=request, scope=scope, sha256=sha256)
        upload = UploadTarget(method="PUT", url=url, headers={"content-type": _OCTET_STREAM})
        missing.append(MissingBlob(sha256=sha256, size=sizes[sha256], upload=upload))
    return MissingBlobsResult(missing=missing)
