"""Decode the `resources` a request submits with its bundle: the files its steps read, such as a template file.

The wire form is a JSON object mapping each file's bundle-relative path, the exact path a step names (a
`PipeDocGen` step's `template_file`), to the file's bytes in standard base64. Every bundle of the request is read
as sitting in one directory. The decoded files go to the runtime as `BundleResources`, which refuses a file none of
the bundle's steps names once the bundle is parsed.

Refusals, in the order they are checked:

- more files than `MAX_RESOURCES_PER_REQUEST` → 413 `PayloadTooLarge`;
- a path that cannot name a file inside the bundle (absolute, a `..` segment, a backslash, a colon, empty, or a
  second spelling of a path already submitted) → 422 `InvalidResourcePath`;
- a file whose encoded length already exceeds the per-file ceiling → 413 `PayloadTooLarge`, before decoding;
- a value that is not valid base64 → 400 `InvalidBase64`, as `bundle_b64` is;
- a decoded file over `MAX_RESOURCE_FILE_BYTES`, or a running total over `MAX_RESOURCES_TOTAL_BYTES` → 413.
"""

import base64
import binascii

from pipelex import log
from pipelex.core.bundle_resources.bundle_resource import BundleResources, canonical_resource_path, make_bundle_resources
from pipelex.core.bundle_resources.exceptions import BundleResourcePathError
from pipelex.tools.log.error_fields import error_fields

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_bad_request, raise_payload_too_large, raise_validation_error
from pipelex_api.limits import MAX_RESOURCE_FILE_BYTES, MAX_RESOURCES_PER_REQUEST, MAX_RESOURCES_TOTAL_BYTES

# Base64 inflates by 4/3, so a file within the ceiling encodes to at most this many characters (+4 covers padding).
# Checking the encoded length first refuses an oversized file before it is decoded into memory.
_MAX_RESOURCE_B64_CHARS = MAX_RESOURCE_FILE_BYTES * 4 // 3 + 4


def decode_bundle_resources(*, resources: dict[str, str] | None) -> BundleResources | None:
    """The files a request submits with its bundle, decoded and keyed by canonical path, or None when it submits none."""
    if not resources:
        return None
    if len(resources) > MAX_RESOURCES_PER_REQUEST:
        raise_payload_too_large(message=f"resources exceeds the {MAX_RESOURCES_PER_REQUEST}-file limit (got {len(resources)})")
    files: dict[str, bytes] = {}
    total_bytes = 0
    for path, encoded in resources.items():
        try:
            canonical_resource_path(path=path)
        except BundleResourcePathError as exc:
            raise_validation_error(message=exc.message, error_type=ErrorType.INVALID_RESOURCE_PATH)
        if len(encoded) > _MAX_RESOURCE_B64_CHARS:
            raise_payload_too_large(message=f"The file '{path}' in resources exceeds the {MAX_RESOURCE_FILE_BYTES // 1024} KiB per-file limit")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as decode_error:
            # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
            log.debug("A submitted file's base64 could not be decoded", fields=error_fields(exc=decode_error))
            raise_bad_request(message=f"The file '{path}' in resources is not valid base64", error_type=ErrorType.INVALID_BASE64)
        if len(data) > MAX_RESOURCE_FILE_BYTES:
            raise_payload_too_large(message=f"The file '{path}' in resources exceeds the {MAX_RESOURCE_FILE_BYTES // 1024} KiB per-file limit")
        total_bytes += len(data)
        if total_bytes > MAX_RESOURCES_TOTAL_BYTES:
            raise_payload_too_large(message=f"resources exceeds the {MAX_RESOURCES_TOTAL_BYTES // 1024} KiB total-size limit")
        files[path] = data
    try:
        return make_bundle_resources(files=files)
    except BundleResourcePathError as exc:
        raise_validation_error(message=exc.message, error_type=ErrorType.INVALID_RESOURCE_PATH)
