"""Inputs of a hosted run: find the local files they name, anchor them, and upload them before the run.

A hosted run cannot read this machine's files, so a document or an image given as a local path must be uploaded
first, and the run given the storage URI instead. Where a file sits is the pipe's signature to say, so the input-form
descriptor `POST /v1/pipe-io` answers guides a walk over the inputs: each local path at a document or image position is
anchored as a local run reads it (a relative path in an inputs file against that file's directory, a `file://` URI as
the path it names, `~` expanded), uploaded once with the SDK's `upload_file`, and rewritten to canonical content
carrying the storage URI. Every other value, an explicit `null` included, reaches the run as the caller wrote it.

The signature is read only when it can matter: when some string of the inputs, at any depth, names an existing file on
this machine. Any other inputs go straight to the run, which keeps pipe-io out of a run that uploads nothing; pipe-io
cannot load a method calling another one by its address, which the run route fetches and runs.
"""

import contextlib
import os
import re
from pathlib import Path
from typing import Any, NamedTuple, Protocol, cast

from mthds.protocol.input_form import (
    BooleanItem,
    DateItem,
    DocumentItem,
    EnumItem,
    ImageItem,
    InputFormItem,
    ListItem,
    NumberItem,
    ObjectItem,
    PipeInputFormDescriptor,
    ProseItem,
    TextItem,
    UnknownItem,
)
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.crate_models import CrateInvalidReport, MthdsFileItem, PipeIORequest
from pipelex_sdk.upload import UploadRecord

from pipelex.hosted.exceptions import HostedLocalFileUploadUnavailableError, HostedMethodInvalidError
from pipelex.tools.uri.resolved_uri import ResolvedLocalPath
from pipelex.tools.uri.uri_resolver import resolve_uri

#: An `http(s)://` URL, which the hosted API fetches itself. Matched as the SDK matches it, whatever the case of the
#: scheme.
_HTTP_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
#: The other source forms that are not files on this machine, matched as the SDK matches them, case included: a storage
#: URI, and a data URL, which carries its bytes and reaches the run as it is.
_NOT_LOCAL_PREFIXES: tuple[str, ...] = ("pipelex-storage://", "data:")
#: A `file://` URI, which a local run reads as the local path it names.
_FILE_URI_PREFIX = "file://"
#: What the crate core behind `POST /v1/pipe-io` says when it refuses a method calling another one by its address
#: (`pipelex/pipeline/resolve_bundle.py`). The run route fetches such a dependency; pipe-io cannot load it.
ADDRESS_DEPENDENCY_REFUSAL_MARKER = "address-based dependency"
#: The dependency's address, as that refusal quotes it.
_REFUSED_DEPENDENCY_PATTERN = re.compile(re.escape(ADDRESS_DEPENDENCY_REFUSAL_MARKER) + r" '([^']+)'")


class AnchoredInputs(NamedTuple):
    """Inputs with every local file at a file position anchored, and the local files found, in walk order."""

    inputs: dict[str, Any]
    local_sources: list[str]


class PreparedHostedInputs(NamedTuple):
    """What a hosted run sends as inputs, the files uploaded for it, and the qualified pipe its signature was read from."""

    inputs: dict[str, Any] | None
    uploads: list[UploadRecord]
    #: The qualified ref of the pipe whose signature was read, `None` when the inputs named no local file to read it for.
    pipe_ref: str | None


class _FilePositionVisitor(Protocol):
    """What the descriptor walk does with a value the signature declares a document or an image."""

    def __call__(self, *, value: Any) -> Any: ...


def _local_path_reference(*, source: str, base_dir: Path | None) -> str | None:
    """The local path a source names, anchored to `base_dir` when relative; `None` for a form that is not a local file.

    A `file://` URI is decoded to its path, as a local run decodes it, and `~` is expanded, leaving a `~user` whose
    home is unknown as it is rather than failing.
    """
    if source.startswith(_NOT_LOCAL_PREFIXES) or _HTTP_URL_PATTERN.match(source):
        return None
    if source.startswith(_FILE_URI_PREFIX):
        resolved = resolve_uri(source)
        if isinstance(resolved, ResolvedLocalPath):
            source = resolved.path
    path = Path(source)
    with contextlib.suppress(RuntimeError):
        # A `~user` whose home is unknown stays as written: any text of the inputs is asked about, not only paths.
        path = path.expanduser()
    if base_dir is not None and not path.is_absolute():
        path = base_dir / path
    return str(path)


def _names_an_existing_local_file(*, source: str, base_dir: Path | None) -> bool:
    """Whether a string names a file on this machine, from `base_dir` or from the working directory.

    `os.path.isfile` answers `False` for a value no path can be (one too long, one carrying a NUL byte), so any text
    is safe to ask about. `Path.is_file` raises on a name too long before Python 3.13, so it is not used here.
    """
    candidates = {_local_path_reference(source=source, base_dir=base_dir), _local_path_reference(source=source, base_dir=None)}
    return any(candidate is not None and os.path.isfile(candidate) for candidate in candidates)  # ruff: ignore[os-path-isfile]


def _value_names_a_local_file(*, value: Any, base_dir: Path | None) -> bool:
    if isinstance(value, str):
        return _names_an_existing_local_file(source=value, base_dir=base_dir)
    if isinstance(value, dict):
        return any(_value_names_a_local_file(value=member, base_dir=base_dir) for member in cast("dict[str, Any]", value).values())
    if isinstance(value, list):
        return any(_value_names_a_local_file(value=element, base_dir=base_dir) for element in cast("list[Any]", value))
    return False


def inputs_name_a_local_file(*, inputs: dict[str, Any], base_dir: Path | None) -> bool:
    """Whether some string of the inputs, at any depth, names an existing file on this machine.

    The test decides whether a hosted run reads its pipe's signature before it starts, so it reads no signature: it
    looks at every string, whatever its position, and counts one that is not an `http(s)://` URL, a
    `pipelex-storage://` URI or a `data:` URL and names a file under `base_dir` (the inputs file's directory) or the
    working directory. A `file://` URI counts by the path it names.
    """
    return _value_names_a_local_file(value=inputs, base_dir=base_dir)


def _anchor_source(*, source: str, base_dir: Path | None, local_sources: list[str]) -> str:
    """A source at a file position, a local path anchored to `base_dir` and recorded, any other form unchanged."""
    anchored = _local_path_reference(source=source, base_dir=base_dir)
    if anchored is None:
        return source
    local_sources.append(anchored)
    return anchored


def _anchor_file_position(*, value: Any, base_dir: Path | None, local_sources: list[str]) -> Any:
    """A value the signature declares a document or an image: a path string, or content whose `url` is one."""
    if isinstance(value, str):
        return _anchor_source(source=value, base_dir=base_dir, local_sources=local_sources)
    if isinstance(value, dict):
        content = cast("dict[str, Any]", value)
        url = content.get("url")
        if isinstance(url, str):
            return {**content, "url": _anchor_source(source=url, base_dir=base_dir, local_sources=local_sources)}
        return content
    # `None` (an optional file left out) and any other shape are left for the run to read: preparation never
    # second-guesses the signature.
    return value


def _walk_node(*, node: InputFormItem, value: Any, at_file_position: _FilePositionVisitor) -> Any:
    """Walk one value against its descriptor node, the way the SDK's preparation walks it.

    The match is over the item classes, which the per-kind named fields derive from, so one set of patterns covers a
    named position and a list's nameless item alike. An `unknown` node is a dynamic input whose signature declares no
    file, and it is not entered, as the SDK does not enter it.
    """
    match node:
        case DocumentItem() | ImageItem():
            return at_file_position(value=value)
        case ObjectItem():
            if not isinstance(value, dict):
                return value
            caller_dict = cast("dict[str, Any]", value)
            walked: dict[str, Any] = dict(caller_dict)
            for field in node.fields:
                if field.name in caller_dict:
                    walked[field.name] = _walk_node(node=field, value=caller_dict[field.name], at_file_position=at_file_position)
            return walked
        case ListItem():
            if not isinstance(value, list):
                return value
            elements = cast("list[Any]", value)
            return [_walk_node(node=node.item, value=element, at_file_position=at_file_position) for element in elements]
        case TextItem() | ProseItem() | DateItem() | NumberItem() | BooleanItem() | EnumItem() | UnknownItem():
            return value


def _is_explicit_envelope(*, value: Any) -> bool:
    """The explicit `{concept, content}` input envelope: exactly those two keys, as the runtime's input shaper reads it."""
    return isinstance(value, dict) and set(cast("dict[str, Any]", value)) == {"concept", "content"}


def _walk_inputs(*, inputs: dict[str, Any], descriptor: PipeInputFormDescriptor, at_file_position: _FilePositionVisitor) -> dict[str, Any]:
    """Walk each declared input against its descriptor field, an explicit envelope through its content; a copy."""
    declared = {field.name: field for field in descriptor.fields}
    walked: dict[str, Any] = dict(inputs)
    for name, caller_value in inputs.items():
        field = declared.get(name)
        if field is None:
            continue
        if _is_explicit_envelope(value=caller_value):
            envelope = cast("dict[str, Any]", caller_value)
            walked[name] = {**envelope, "content": _walk_node(node=field, value=envelope["content"], at_file_position=at_file_position)}
        else:
            walked[name] = _walk_node(node=field, value=caller_value, at_file_position=at_file_position)
    return walked


def anchor_local_file_sources(*, inputs: dict[str, Any], descriptor: PipeInputFormDescriptor, base_dir: Path | None) -> AnchoredInputs:
    """Anchor the local files named at the file positions `descriptor` declares, and list them.

    Args:
        inputs: The caller's inputs, compact or in an explicit `{concept, content}` envelope per input. Not mutated.
        descriptor: The input form of the pipe that runs.
        base_dir: The directory a relative path resolves against: the inputs file's, or `None` for inline inputs,
            whose relative paths stay relative to the working directory as on a local run.

    Returns:
        A copy of the inputs with each local path at a file position anchored: a relative one joined to `base_dir`, a
        `file://` URI decoded to its path, `~` expanded. And every local file found, anchored, in walk order. A
        `pipelex-storage://` URI, an `http(s)://` URL (whatever the case of its scheme), a `data:` URL and a `null`
        are not local files. A value at a position the signature does not declare a file is never touched, whatever
        it looks like.
    """
    local_sources: list[str] = []

    def _anchor(*, value: Any) -> Any:
        return _anchor_file_position(value=value, base_dir=base_dir, local_sources=local_sources)

    anchored = _walk_inputs(inputs=inputs, descriptor=descriptor, at_file_position=_anchor)
    return AnchoredInputs(inputs=anchored, local_sources=local_sources)


def _with_storage_uris(*, anchored: AnchoredInputs, descriptor: PipeInputFormDescriptor, uri_by_source: dict[str, str]) -> dict[str, Any]:
    """The anchored inputs with each uploaded file rewritten to canonical content carrying its storage URI, as the SDK writes it."""

    def _rewrite(*, value: Any) -> Any:
        if isinstance(value, str):
            uri = uri_by_source.get(value)
            return value if uri is None else {"url": uri}
        if isinstance(value, dict):
            content = cast("dict[str, Any]", value)
            url = content.get("url")
            if isinstance(url, str) and url in uri_by_source:
                return {**content, "url": uri_by_source[url]}
            return content
        return value

    return _walk_inputs(inputs=anchored.inputs, descriptor=descriptor, at_file_position=_rewrite)


def _address_dependency_refusal(*, report: CrateInvalidReport) -> HostedLocalFileUploadUnavailableError | None:
    """The error to raise when pipe-io refused the method for calling another one by its address, else `None`.

    The run route fetches such a dependency, so the method is not at fault. The refusal's own advice, to send the
    dependency's contents, is meant for the API's callers, so the error names the dependency and leaves the advice out.
    """
    messages = [report.message, *(item.message for item in report.validation_errors)]
    refusal = next((message for message in messages if ADDRESS_DEPENDENCY_REFUSAL_MARKER in message), None)
    if refusal is None:
        return None
    msg = "Local file upload is not available yet for methods with address-based dependencies, and the inputs name a local file"
    if dependency := _REFUSED_DEPENDENCY_PATTERN.search(refusal):
        msg += f": this method depends on {dependency.group(1)}"
    return HostedLocalFileUploadUnavailableError(msg)


async def prepare_hosted_inputs(
    *,
    client: PipelexAPIClient,
    mthds_files: list[MthdsFileItem] | None,
    method_ref: str | None,
    method_id: str | None,
    pipe_code: str | None,
    inputs: dict[str, Any] | None,
    inputs_base_dir: Path | None,
) -> PreparedHostedInputs:
    """Upload the local files a hosted run's inputs name, and hand back the inputs to send.

    Inputs naming no existing file on this machine go as they are, with no request. Otherwise one `POST /v1/pipe-io`
    reads the signature of the pipe that runs, `pipe_code` or the method's entry pipe; each local file at a file
    position is uploaded once with `upload_file` and rewritten to its `pipelex-storage://` URI, and every other value
    is sent as written. A method whose signature does not resolve is refused here, before any run starts: pipe-io's
    verdict names each faulty file by the label it was sent under, which the run route, taking the files as bare
    contents, cannot do.

    Raises:
        HostedLocalFileUploadUnavailableError: If pipe-io cannot load the method because it calls another method by
            its address: the run route would, so the file has to reach it as a URL.
        HostedMethodInvalidError: If the method does not load, with the hosted API's labelled validation items.
        ApiResponseError: If the hosted API refuses the pipe-io request (an unknown method, a key it refuses).
        InputPreparationError: If an upload fails, or a local file cannot be read.
    """
    if not inputs or not inputs_name_a_local_file(inputs=inputs, base_dir=inputs_base_dir):
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=None)

    report = await client.pipe_io(PipeIORequest(files=mthds_files, method_ref=method_ref, method_id=method_id, pipe_ref=pipe_code))
    if isinstance(report, CrateInvalidReport):
        if (address_dependency_refusal := _address_dependency_refusal(report=report)) is not None:
            raise address_dependency_refusal
        msg = f"The hosted API cannot load the method: {report.message}"
        raise HostedMethodInvalidError(msg, validation_errors=report.validation_errors)
    selected_pipe_ref = report.pipe_ref
    descriptor = report.input_form.get(selected_pipe_ref) if selected_pipe_ref is not None else None
    if descriptor is None:
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=selected_pipe_ref)

    anchored = anchor_local_file_sources(inputs=inputs, descriptor=descriptor, base_dir=inputs_base_dir)
    if not anchored.local_sources:
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=selected_pipe_ref)

    uploads: list[UploadRecord] = []
    uri_by_source: dict[str, str] = {}
    for local_source in anchored.local_sources:
        if local_source in uri_by_source:
            continue
        record = await client.upload_file(local_source)
        uploads.append(record)
        uri_by_source[local_source] = record.uri
    prepared_inputs = _with_storage_uris(anchored=anchored, descriptor=descriptor, uri_by_source=uri_by_source)
    return PreparedHostedInputs(inputs=prepared_inputs, uploads=uploads, pipe_ref=selected_pipe_ref)
