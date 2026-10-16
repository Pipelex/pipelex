"""Decode a `bundle_b64` archive into its entries, under the guards a zip archive needs.

A run request may carry its method as `bundle_b64`, a base64-encoded zip archive of the method's folder, beside the
map of file entries `files` that replaces it. This module only opens the archive: it bounds the encoded string before
decoding it, refuses an archive with too many members, and reads each member through a bounded stream so a zip bomb
whose header under-reports its size cannot decompress past the ceiling. The entries it returns keep the names the
archive gives them; `pipelex_api.method_tree_request` reads them as a map of file entries, so the archive's names are
judged by the one rule of the method tree, as the keys of `files` are: a name that is not a tree path, or that names a
file the membership rule keeps out of every tree, is refused, and so is one name given twice.

Nothing here writes to disk, imports or executes the archive's Python.
"""

import base64
import binascii
import zipfile
from io import BytesIO

from pipelex import log
from pipelex.tools.log.error_fields import error_fields

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_bad_request, raise_payload_too_large, raise_validation_error
from pipelex_api.limits import MAX_BUNDLE_FILES, MAX_BUNDLE_TOTAL_BYTES

# Base64 inflates by 4/3; a zip is compressed, so a bundle whose DECOMPRESSED content is within
# the ceiling encodes to well under this. Bounding the base64 string BEFORE decoding stops a
# ~100 MiB request-body (the only other bound) from being expanded into ~75 MiB of heap just to
# be rejected later by the decompressed-size guard. Slack (+4) covers padding.
_MAX_BUNDLE_B64_CHARS = MAX_BUNDLE_TOTAL_BYTES * 4 // 3 + 4


def _guard_count(count: int) -> None:
    if count == 0:
        raise_validation_error(message="Bundle is empty (no files)", error_type=ErrorType.INVALID_BUNDLE)
    if count > MAX_BUNDLE_FILES:
        raise_payload_too_large(message=f"Bundle exceeds the {MAX_BUNDLE_FILES}-file limit (got {count})")


def _guard_running_total(total_bytes: int) -> None:
    if total_bytes > MAX_BUNDLE_TOTAL_BYTES:
        raise_payload_too_large(message=f"Bundle exceeds the {MAX_BUNDLE_TOTAL_BYTES // 1024} KiB decompressed-size limit")


def decode_bundle_archive(*, bundle_b64: str) -> list[tuple[str, bytes]]:
    """Decode a base64 zip and return its file members as `(name, bytes)`, in archive order, directories skipped.

    Zip-bomb guard: each member is read through a bounded stream so a lying uncompressed-size header cannot force
    unbounded decompression — the running total is checked against `MAX_BUNDLE_TOTAL_BYTES` as bytes are pulled. A
    cheap length check on the still-encoded string runs FIRST, so an oversized payload is refused before it is buffered
    into memory as decoded bytes. A name the archive gives twice is returned twice, for the tree's reader to refuse.

    Raises (as problem documents): an oversized archive (413 `PayloadTooLarge`), a value that is not base64 (400
    `InvalidBase64`), and one that is not a zip archive or holds no file (422 `InvalidBundle`).
    """
    if len(bundle_b64) > _MAX_BUNDLE_B64_CHARS:
        raise_payload_too_large(message=f"bundle_b64 exceeds the {MAX_BUNDLE_TOTAL_BYTES // 1024} KiB compressed-size limit")
    try:
        raw = base64.b64decode(bundle_b64, validate=True)
    except (binascii.Error, ValueError) as decode_error:
        # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
        log.debug("A bundle's base64 could not be decoded", fields=error_fields(exc=decode_error))
        raise_bad_request(message="bundle_b64 is not valid base64", error_type=ErrorType.INVALID_BASE64)

    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as zip_error:
        # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
        log.debug("A bundle is not a valid zip archive", fields=error_fields(exc=zip_error))
        raise_validation_error(message="bundle_b64 is not a valid zip archive", error_type=ErrorType.INVALID_BUNDLE)

    entries: list[tuple[str, bytes]] = []
    total_bytes = 0
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        _guard_count(len(members))
        budget = MAX_BUNDLE_TOTAL_BYTES
        for info in members:
            # Bounded read: pull at most (remaining budget + 1) bytes so a zip bomb whose header
            # under-reports its size still cannot decompress past the ceiling.
            with archive.open(info) as member:
                data = member.read(budget + 1)
            total_bytes += len(data)
            _guard_running_total(total_bytes)
            budget = MAX_BUNDLE_TOTAL_BYTES - total_bytes
            entries.append((info.filename, data))
    return entries
