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

from mthds.protocol.problem.registry import CoreCode, RequestMalformedReason
from pipelex import log
from pipelex.tools.log.error_fields import error_fields

from pipelex_api.exceptions import MethodPackageReason, RequestMethodError, RunnerRequestError
from pipelex_api.limits import MAX_BUNDLE_FILES, MAX_BUNDLE_TOTAL_BYTES

# The request field the archive rides, which the refusals of its encoding name.
_BUNDLE_FIELD = "bundle_b64"

# Base64 inflates by 4/3; a zip is compressed, so a bundle whose DECOMPRESSED content is within
# the ceiling encodes to well under this. Bounding the base64 string BEFORE decoding stops a
# ~100 MiB request-body (the only other bound) from being expanded into ~75 MiB of heap just to
# be rejected later by the decompressed-size guard. Slack (+4) covers padding.
_MAX_BUNDLE_B64_CHARS = MAX_BUNDLE_TOTAL_BYTES * 4 // 3 + 4


def _guard_count(count: int) -> None:
    if count == 0:
        msg = "Bundle is empty (no files)"
        raise RunnerRequestError(msg, field=_BUNDLE_FIELD)
    if count > MAX_BUNDLE_FILES:
        msg = f"Bundle exceeds the {MAX_BUNDLE_FILES}-file limit (got {count})"
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.BUNDLE_TOO_MANY_FILES, limit=MAX_BUNDLE_FILES)


def _guard_running_total(total_bytes: int) -> None:
    if total_bytes > MAX_BUNDLE_TOTAL_BYTES:
        msg = f"Bundle exceeds the {MAX_BUNDLE_TOTAL_BYTES // 1024} KiB decompressed-size limit"
        raise RequestMethodError(msg).with_params(reason=MethodPackageReason.BUNDLE_TOO_LARGE, limit=MAX_BUNDLE_TOTAL_BYTES)


def decode_bundle_archive(*, bundle_b64: str) -> list[tuple[str, bytes]]:
    """Decode a base64 zip and return its file members as `(name, bytes)`, in archive order, directories skipped.

    Zip-bomb guard: each member is read through a bounded stream so a lying uncompressed-size header cannot force
    unbounded decompression — the running total is checked against `MAX_BUNDLE_TOTAL_BYTES` as bytes are pulled. A
    cheap length check on the still-encoded string runs FIRST, so an oversized payload is refused before it is buffered
    into memory as decoded bytes. A name the archive gives twice is returned twice, for the tree's reader to refuse.

    Raises (as problem documents): an encoded archive past the size limit (413 `request.too_large`), a value that is
    not base64 or not a zip archive (422 `request.malformed`), an archive holding no file (422 `request.invalid`), and
    one past the limit on its files or on its decompressed size (422 `method.package_invalid`).
    """
    if len(bundle_b64) > _MAX_BUNDLE_B64_CHARS:
        msg = f"bundle_b64 exceeds the {MAX_BUNDLE_TOTAL_BYTES // 1024} KiB compressed-size limit"
        raise (
            RunnerRequestError(msg, field=_BUNDLE_FIELD)
            .with_error_code(CoreCode.REQUEST_TOO_LARGE)
            .with_params(limit=_MAX_BUNDLE_B64_CHARS, size=len(bundle_b64))
        )
    try:
        raw = base64.b64decode(bundle_b64, validate=True)
    except (binascii.Error, ValueError) as decode_error:
        # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
        log.debug("A bundle's base64 could not be decoded", fields=error_fields(exc=decode_error))
        msg = "bundle_b64 is not valid base64"
        raise (
            RunnerRequestError(msg, field=_BUNDLE_FIELD)
            .with_error_code(CoreCode.REQUEST_MALFORMED)
            .with_params(reason=RequestMalformedReason.BAD_BASE64)
        ) from decode_error

    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as zip_error:
        # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
        log.debug("A bundle is not a valid zip archive", fields=error_fields(exc=zip_error))
        msg = "bundle_b64 is not a valid zip archive"
        raise (
            RunnerRequestError(msg, field=_BUNDLE_FIELD)
            .with_error_code(CoreCode.REQUEST_MALFORMED)
            .with_params(reason=RequestMalformedReason.BAD_ZIP)
        ) from zip_error

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
