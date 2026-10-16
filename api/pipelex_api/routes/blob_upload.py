"""`PUT /v1/blobs/{sha256}`: one blob's bytes, uploaded to the target `POST /v1/blobs/missing` named (MTHDS Protocol).

This router mounts OUTSIDE the authenticated composite `/v1` router, like `/v1/version`: the upload is authorized by
the signed query of its target (`pipelex_api.blob_upload`), which only a caller who passed the deployment's
authentication on `POST /v1/blobs/missing` holds, so a sender uploads with exactly the headers the target names. The
bytes are written under the scope the signature binds, whole: a blob is never changed, so uploading bytes the runner
already holds at their size succeeds and changes nothing, and only bytes held short, which a storage that does not
publish writes whole could leave, are written over. Only `blobs/` is ever written here, never a tree's listing under `trees/`,
so an uploaded file that happens to read as a listing proves nothing.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response
from mthds.method_tree.digest import sha256_hex

from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.blob_upload import EXPIRES_PARAM, SCOPE_PARAM, SIGNATURE_PARAM, is_upload_authorized
from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_forbidden, raise_validation_error
from pipelex_api.limits import MAX_METHOD_TREE_FILE_BYTES
from pipelex_api.openapi_responses import PROBLEM_403_BLOB_UPLOAD, PROBLEM_413, PROBLEM_422, PROBLEM_500

router = APIRouter(tags=["blobs"])

SHA256_PATTERN = r"^[0-9a-f]{64}$"


@router.put(
    "/blobs/{sha256}",
    status_code=204,
    response_class=Response,
    summary="Upload one blob's bytes to the target POST /blobs/missing named.",
    # Mounted outside the composite `/v1` router, so it inherits none of its shared problem responses: it declares
    # the statuses it can produce itself, and never answers 401.
    responses={403: PROBLEM_403_BLOB_UPLOAD, 413: PROBLEM_413, 422: PROBLEM_422, 500: PROBLEM_500},
    openapi_extra={
        "x-mthds-protocol": True,
        "requestBody": {
            "required": True,
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        },
    },
)
async def put_blob(
    request: Request,
    sha256: Annotated[str, Path(pattern=SHA256_PATTERN, description="The SHA-256 of the body, in lowercase hexadecimal.")],
    scope: Annotated[str | None, Query(alias=SCOPE_PARAM, description="The blob store's scope, as the signed target names it.")] = None,
    expires: Annotated[str | None, Query(alias=EXPIRES_PARAM, description="When the target expires, in seconds since the epoch.")] = None,
    signature: Annotated[str | None, Query(alias=SIGNATURE_PARAM, description="The target's signature.")] = None,
) -> Response:
    """Store one blob's bytes under its SHA-256, as the upload target `POST /v1/blobs/missing` named (MTHDS Protocol).

    The body is the blob's bytes and nothing else. A target whose signature does not hold, or that has expired, is a
    403 `BlobUploadNotAuthorized`, as is a query that is not one this runner signs, such as an expiry that is not a
    decimal integer; a body past `MAX_METHOD_TREE_FILE_KIB` a 422 `MethodTreeTooLarge`; and a body whose SHA-256 is not
    the path's a 422 `BlobMismatch`. A blob is never changed: uploading bytes the runner already holds answers 204 and
    changes nothing.
    """
    if not is_upload_authorized(scope=scope, sha256=sha256, expires=expires, signature=signature) or scope is None:
        msg = "This upload carries no valid target: ask POST /v1/blobs/missing for one, and upload to the URL it names before it expires."
        raise_forbidden(message=msg, error_type=ErrorType.BLOB_UPLOAD_NOT_AUTHORIZED)
    body = await request.body()
    if len(body) > MAX_METHOD_TREE_FILE_BYTES:
        msg = f"The blob holds {len(body)} bytes, past this runner's limit of {MAX_METHOD_TREE_FILE_BYTES // 1024} KiB for one file of a method tree."
        raise_validation_error(message=msg, error_type=ErrorType.METHOD_TREE_TOO_LARGE)
    if sha256_hex(body) != sha256:
        msg = f"The body's SHA-256 is not {sha256}, the hash the path names: nothing was stored."
        raise_validation_error(message=msg, error_type=ErrorType.BLOB_MISMATCH)
    await RunnerBlobStore.make_for_scope(scope=scope).store_blob(data=body)
    return Response(status_code=204)
