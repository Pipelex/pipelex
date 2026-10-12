"""Decode the files a request submits with its bundle that its steps read, such as a template file.

They come in two ways. `resources` is a JSON object mapping each file's bundle-relative path, the exact path a step
names (a `PipeDocGen` step's `template_file`), to the file's bytes in standard base64, beside `mthds_contents` or a
method bundle. A method bundle (`bundle_b64` or `files`) may also ship the file beside its `.mthds` file, which
`files_its_steps_read` picks out. Every bundle of the request is read as sitting in one directory, so one path holds
one file. The decoded files go to the runtime as `BundleResources`, which refuses a file none of the bundle's steps
names once the bundle is parsed.

Refusals, in the order they are checked:

- more `resources` than `MAX_RESOURCES_PER_REQUEST` → 413 `PayloadTooLarge`;
- a path that cannot name a file inside the bundle (absolute, a `..` segment, a backslash, a colon, empty, or a
  second spelling of a path already submitted) → 422 `InvalidResourcePath`, before any value is decoded;
- more files than `MAX_RESOURCES_PER_REQUEST`, counting those the method bundle ships → 413 `PayloadTooLarge`;
- a file whose encoded length already exceeds the per-file ceiling → 413 `PayloadTooLarge`, before decoding;
- a value that is not valid base64 → 400 `InvalidBase64`, as `bundle_b64` is;
- two different files under one path, sent in `resources` and shipped in the bundle, or shipped beside two of its
  `.mthds` files → 422 `InvalidResourcePath`;
- a decoded or shipped file over `MAX_RESOURCE_FILE_BYTES`, or a running total over `MAX_RESOURCES_TOTAL_BYTES` → 413.
"""

import base64
import binascii
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import NoReturn

from pipelex import log
from pipelex.core.bundle_resources.bundle_resource import (
    BundleResources,
    canonical_resource_path,
    canonical_resource_path_or_none,
    make_bundle_resources,
)
from pipelex.core.bundle_resources.exceptions import BundleResourcePathError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.tools.log.error_fields import error_fields

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_bad_request, raise_payload_too_large, raise_validation_error
from pipelex_api.limits import MAX_RESOURCE_FILE_BYTES, MAX_RESOURCES_PER_REQUEST, MAX_RESOURCES_TOTAL_BYTES

# Base64 inflates by 4/3, so a file within the ceiling encodes to at most this many characters (+4 covers padding).
# Checking the encoded length first refuses an oversized file before it is decoded into memory.
_MAX_RESOURCE_B64_CHARS = MAX_RESOURCE_FILE_BYTES * 4 // 3 + 4


def _refuse_two_files_under_one_path(*, path: str, where: str) -> NoReturn:
    msg = (
        f"Two different files are named '{path}', {where}. Every bundle of a request reads its files as if it sat in one "
        "directory, so a path names one file: send one of them, or rename one and the step that reads it."
    )
    raise_validation_error(message=msg, error_type=ErrorType.INVALID_RESOURCE_PATH)


def files_its_steps_read(
    *, mthds_entries: Iterable[tuple[PurePosixPath, str]], other_entries: Iterable[tuple[PurePosixPath, bytes]]
) -> dict[str, bytes]:
    """The files a method bundle ships beside its `.mthds` files that their steps read, keyed by the path a step names.

    Each `.mthds` file is parsed for the files its steps name, such as a `PipeDocGen` step's `template_file`, which is
    looked up relative to that file's own directory in the bundle. The bundle's `.mthds` files load as content strings,
    so these files travel with them as the `resources` a request sends do, wherever the run goes. A file a step names
    that the bundle does not ship is left out, for `resources` to supply or the load to refuse saying so, and a `.mthds`
    file that does not parse is skipped, for the load to give its verdict on.

    Raises (as a 422 `InvalidResourcePath`): two steps naming one path, beside two `.mthds` files that ship different files.
    """
    shipped = dict(other_entries)
    files: dict[str, bytes] = {}
    for mthds_relpath, mthds_content in mthds_entries:
        try:
            blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
        except MthdsParserError as exc:
            log.debug("A method bundle's file did not parse, so the files its steps read are left to its load", fields=error_fields(exc=exc))
            continue
        for pipe_blueprint in (blueprint.pipe or {}).values():
            for named_path in pipe_blueprint.bundle_resource_reads:
                canonical_path = canonical_resource_path_or_none(path=named_path)
                if canonical_path is None:
                    continue
                data = shipped.get(mthds_relpath.parent / canonical_path)
                if data is None:
                    continue
                known = files.get(canonical_path)
                if known is not None and known != data:
                    _refuse_two_files_under_one_path(path=canonical_path, where="shipped beside two of the bundle's .mthds files")
                files[canonical_path] = data
    return files


def decode_bundle_resources(*, resources: dict[str, str] | None, bundle_files: Mapping[str, bytes] | None = None) -> BundleResources | None:
    """The files the bundle's steps read, decoded and keyed by canonical path, or None when there are none.

    `resources` are the ones the request sends, in base64. `bundle_files` are the ones its method bundle ships, as
    `files_its_steps_read` picks them out. Both are held to the same limits, together, and a file in both must be the same.
    """
    if not resources and not bundle_files:
        return None
    sent = resources or {}
    shipped = bundle_files or {}
    if len(sent) > MAX_RESOURCES_PER_REQUEST:
        raise_payload_too_large(message=f"resources exceeds the {MAX_RESOURCES_PER_REQUEST}-file limit (got {len(sent)})")
    # Every path first, so a second spelling of one file is refused as such before any value is decoded.
    sent_by_path: dict[str, tuple[str, str]] = {}
    for path, encoded in sent.items():
        try:
            canonical_path = canonical_resource_path(path=path)
        except BundleResourcePathError as exc:
            raise_validation_error(message=exc.message, error_type=ErrorType.INVALID_RESOURCE_PATH)
        if canonical_path in sent_by_path:
            msg = f"Two files submitted with the bundle name the same file '{canonical_path}'."
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_RESOURCE_PATH)
        sent_by_path[canonical_path] = (path, encoded)
    file_count = len(sent_by_path.keys() | shipped.keys())
    if file_count > MAX_RESOURCES_PER_REQUEST:
        msg = (
            f"The files the bundle's steps read, in resources and in the bundle, exceed the {MAX_RESOURCES_PER_REQUEST}-file limit (got {file_count})"
        )
        raise_payload_too_large(message=msg)
    files: dict[str, bytes] = {}
    total_bytes = 0
    for canonical_path, (path, encoded) in sent_by_path.items():
        if len(encoded) > _MAX_RESOURCE_B64_CHARS:
            raise_payload_too_large(message=f"The file '{path}' in resources exceeds the {MAX_RESOURCE_FILE_BYTES // 1024} KiB per-file limit")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as decode_error:
            # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
            log.debug("A submitted file's base64 could not be decoded", fields=error_fields(exc=decode_error))
            raise_bad_request(message=f"The file '{path}' in resources is not valid base64", error_type=ErrorType.INVALID_BASE64)
        shipped_data = shipped.get(canonical_path)
        if shipped_data is not None and shipped_data != data:
            _refuse_two_files_under_one_path(path=canonical_path, where="one sent in resources and one shipped in the bundle")
        files[canonical_path] = data
    for canonical_path, data in shipped.items():
        files.setdefault(canonical_path, data)
    for canonical_path, data in files.items():
        if len(data) > MAX_RESOURCE_FILE_BYTES:
            raise_payload_too_large(
                message=f"The file '{canonical_path}' a step reads exceeds the {MAX_RESOURCE_FILE_BYTES // 1024} KiB per-file limit"
            )
        total_bytes += len(data)
        if total_bytes > MAX_RESOURCES_TOTAL_BYTES:
            raise_payload_too_large(message=f"The files the bundle's steps read exceed the {MAX_RESOURCES_TOTAL_BYTES // 1024} KiB total-size limit")
    return make_bundle_resources(files=files)
