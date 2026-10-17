"""Decode the files a request sends in `resources`, the files its bundle's steps read, such as a template file.

`resources` is a JSON object mapping each file's bundle-relative path, the exact path a step names (a `PipeDocGen`
step's `template_file`), to the file's bytes in standard base64. Beside `mthds_contents`, every bundle of the request is
read as sitting in one directory, so one path holds one file, and the decoded files go to the runtime as its
`submitted_files`, keyed by canonical path, which refuses a file none of the bundle's steps names once the bundle is
parsed, and holds the rest as the files of the tree the bundle sits at the root of. Beside a method tree (`files` or
`bundle_b64`), the decoded files join the tree at their paths from its root (`pipelex_api.method_tree_request`), where
the tree's rule judges them as it judges the tree's own files.

Refusals, in the order they are checked:

- more `resources` than `MAX_RESOURCES_PER_REQUEST` → 422 `request.invalid`, naming the field;
- a path that leaves the bundle (absolute, a drive, a `..` segment) → 422 `security.input_path_refused`, with the rule
  it breaks, before any value is decoded, which also logs a security event, as a key of a method tree does;
- a path of the wrong shape (a backslash, a colon, empty, or a second spelling of a path already submitted) → 422
  `request.invalid`, naming the field;
- a file whose encoded length already exceeds the per-file ceiling → 413 `request.too_large`, before decoding;
- a value that is not valid base64 → 422 `request.malformed`, as `bundle_b64` is;
- a decoded file over `MAX_RESOURCE_FILE_BYTES`, or a running total over `MAX_RESOURCES_TOTAL_BYTES` → 413
  `request.too_large`.
"""

import base64
import binascii
from typing import NoReturn

from mthds.protocol.problem.registry import CoreCode, RequestMalformedReason
from pipelex import log
from pipelex.core.bundle_resources.bundle_resource import SUBMITTED_FILES_FIELD, canonical_resource_path
from pipelex.tools.log.error_fields import error_fields

from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.limits import MAX_RESOURCE_FILE_BYTES, MAX_RESOURCES_PER_REQUEST, MAX_RESOURCES_TOTAL_BYTES

# Base64 inflates by 4/3, so a file within the ceiling encodes to at most this many characters (+4 covers padding).
# Checking the encoded length first refuses an oversized file before it is decoded into memory.
_MAX_RESOURCE_B64_CHARS = MAX_RESOURCE_FILE_BYTES * 4 // 3 + 4


def refuse_two_files_under_one_path(*, path: str, where: str) -> NoReturn:
    """Refuse two different files sent under one path, naming the path, with a 422 `request.invalid` on `resources`."""
    msg = (
        f"Two different files are named '{path}', {where}. A path names one file of a method: send one of them, or rename "
        "one and the step that reads it."
    )
    raise RunnerRequestError(msg, field=SUBMITTED_FILES_FIELD)


def _too_large(*, message: str, limit: int, size: int) -> RunnerRequestError:
    """The refusal of submitted files past one of this runner's byte limits, a 413 `request.too_large`."""
    return RunnerRequestError(message, field=SUBMITTED_FILES_FIELD).with_error_code(CoreCode.REQUEST_TOO_LARGE).with_params(limit=limit, size=size)


def decode_bundle_resources(*, resources: dict[str, str] | None) -> dict[str, bytes] | None:
    """The files `resources` sends, decoded and keyed by canonical path, or None when there are none."""
    if not resources:
        return None
    if len(resources) > MAX_RESOURCES_PER_REQUEST:
        # A count, not bytes, so not `request.too_large`, whose parameters are sizes in bytes: the field is refused.
        msg = f"resources exceeds the {MAX_RESOURCES_PER_REQUEST}-file limit (got {len(resources)})"
        raise RunnerRequestError(msg, field=SUBMITTED_FILES_FIELD)
    # Every path first, so a second spelling of one file is refused as such before any value is decoded. A path that
    # leaves the bundle is a security rule's refusal (`security.input_path_refused`), whose security event the error
    # handler logs; one of the wrong shape is the request's (`request.invalid`), and logs none. Both propagate as raised.
    sent_by_path: dict[str, tuple[str, str]] = {}
    for path, encoded in resources.items():
        canonical_path = canonical_resource_path(path=path)
        if canonical_path in sent_by_path:
            msg = f"Two files submitted with the bundle name the same file '{canonical_path}'."
            raise RunnerRequestError(msg, field=SUBMITTED_FILES_FIELD)
        sent_by_path[canonical_path] = (path, encoded)
    files: dict[str, bytes] = {}
    total_bytes = 0
    for canonical_path, (path, encoded) in sent_by_path.items():
        if len(encoded) > _MAX_RESOURCE_B64_CHARS:
            msg = f"The file '{path}' in resources exceeds the {MAX_RESOURCE_FILE_BYTES // 1024} KiB per-file limit"
            raise _too_large(message=msg, limit=_MAX_RESOURCE_B64_CHARS, size=len(encoded))
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as decode_error:
            # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
            log.debug("A submitted file's base64 could not be decoded", fields=error_fields(exc=decode_error))
            msg = f"The file '{path}' in resources is not valid base64"
            raise (
                RunnerRequestError(msg, field=SUBMITTED_FILES_FIELD)
                .with_error_code(CoreCode.REQUEST_MALFORMED)
                .with_params(reason=RequestMalformedReason.BAD_BASE64)
            ) from decode_error
        if len(data) > MAX_RESOURCE_FILE_BYTES:
            msg = f"The file '{canonical_path}' a step reads exceeds the {MAX_RESOURCE_FILE_BYTES // 1024} KiB per-file limit"
            raise _too_large(message=msg, limit=MAX_RESOURCE_FILE_BYTES, size=len(data))
        total_bytes += len(data)
        if total_bytes > MAX_RESOURCES_TOTAL_BYTES:
            msg = f"The files the bundle's steps read exceed the {MAX_RESOURCES_TOTAL_BYTES // 1024} KiB total-size limit"
            raise _too_large(message=msg, limit=MAX_RESOURCES_TOTAL_BYTES, size=total_bytes)
        files[canonical_path] = data
    return files
