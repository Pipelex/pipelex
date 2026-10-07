"""Inputs of a hosted run: find the local files they name, anchor them, and upload them before the run.

A hosted run cannot read this machine's files, so a document or an image given as a local path must be uploaded
first. pipelex-sdk's `prepare_inputs` does the upload, guided by the pipe's input-form descriptor, which states
where a file sits. It reads a relative path from the working directory, though, where a local run reads a path
written in an inputs file from that file's directory. So this module walks the same descriptor first, and only to
anchor each relative path at a file position to the inputs file's directory, and to tell whether there is any local
file at all: inputs naming none are sent as they are, with no upload round trip.
"""

from pathlib import Path
from typing import Any, NamedTuple, cast

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
from pipelex_sdk.crate_models import MthdsFileItem, PipeIORequest, PipeIOValidReport
from pipelex_sdk.upload import UploadRecord

#: The source forms a file position may hold that are not files on this machine: the SDK passes the first three
#: through, and uploads a data URL from the bytes it carries.
_NOT_LOCAL_PREFIXES: tuple[str, ...] = ("pipelex-storage://", "http://", "https://", "data:")


class AnchoredInputs(NamedTuple):
    """Inputs with every local file at a file position anchored, and the local files found, in walk order."""

    inputs: dict[str, Any]
    local_sources: list[str]


class PreparedHostedInputs(NamedTuple):
    """What a hosted run sends as inputs, the files uploaded for it, and the qualified pipe its signature was read from."""

    inputs: dict[str, Any] | None
    uploads: list[UploadRecord]
    pipe_ref: str | None


def _anchor_source(*, source: str, base_dir: Path | None, local_sources: list[str]) -> str:
    """A source at a file position, a local path anchored to `base_dir` and recorded, any other form unchanged."""
    if source.startswith(_NOT_LOCAL_PREFIXES):
        return source
    path = Path(source).expanduser()
    if base_dir is not None and not path.is_absolute():
        path = base_dir / path
    anchored = str(path)
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
    # Any other shape is left for the run to refuse: preparation never second-guesses the signature.
    return value


def _anchor_node(*, node: InputFormItem, value: Any, base_dir: Path | None, local_sources: list[str]) -> Any:
    """Walk one value against its descriptor node, the way the SDK's preparation walks it.

    The match is over the item classes, which the per-kind named fields derive from, so one set of patterns covers a
    named position and a list's nameless item alike. An `unknown` node is a dynamic input whose signature declares no
    file, and it is not entered, as the SDK does not enter it.
    """
    match node:
        case DocumentItem() | ImageItem():
            return _anchor_file_position(value=value, base_dir=base_dir, local_sources=local_sources)
        case ObjectItem():
            if not isinstance(value, dict):
                return value
            caller_dict = cast("dict[str, Any]", value)
            walked: dict[str, Any] = dict(caller_dict)
            for field in node.fields:
                if field.name in caller_dict:
                    walked[field.name] = _anchor_node(node=field, value=caller_dict[field.name], base_dir=base_dir, local_sources=local_sources)
            return walked
        case ListItem():
            if not isinstance(value, list):
                return value
            elements = cast("list[Any]", value)
            return [_anchor_node(node=node.item, value=element, base_dir=base_dir, local_sources=local_sources) for element in elements]
        case TextItem() | ProseItem() | DateItem() | NumberItem() | BooleanItem() | EnumItem() | UnknownItem():
            return value


def _is_explicit_envelope(*, value: Any) -> bool:
    """The explicit `{concept, content}` input envelope: exactly those two keys, as the runtime's input shaper reads it."""
    return isinstance(value, dict) and set(cast("dict[str, Any]", value)) == {"concept", "content"}


def anchor_local_file_sources(*, inputs: dict[str, Any], descriptor: PipeInputFormDescriptor, base_dir: Path | None) -> AnchoredInputs:
    """Anchor the local files named at the file positions `descriptor` declares, and list them.

    Args:
        inputs: The caller's inputs, compact or in an explicit `{concept, content}` envelope per input. Not mutated.
        descriptor: The input form of the pipe that runs.
        base_dir: The directory a relative path resolves against: the inputs file's, or `None` for inline inputs,
            whose relative paths stay relative to the working directory as on a local run.

    Returns:
        A copy of the inputs with each relative local path at a file position joined to `base_dir` (and `~` expanded),
        and every local file found, anchored, in walk order. A `pipelex-storage://`, an `http(s)://` or a `data:` URL
        is not a local file. A value at a position the signature does not declare a file is never touched, whatever it
        looks like.
    """
    declared = {field.name: field for field in descriptor.fields}
    local_sources: list[str] = []
    anchored: dict[str, Any] = dict(inputs)
    for name, caller_value in inputs.items():
        field = declared.get(name)
        if field is None:
            continue
        if _is_explicit_envelope(value=caller_value):
            envelope = cast("dict[str, Any]", caller_value)
            walked_content = _anchor_node(node=field, value=envelope["content"], base_dir=base_dir, local_sources=local_sources)
            anchored[name] = {**envelope, "content": walked_content}
        else:
            anchored[name] = _anchor_node(node=field, value=caller_value, base_dir=base_dir, local_sources=local_sources)
    return AnchoredInputs(inputs=anchored, local_sources=local_sources)


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

    One `POST /v1/pipe-io` reads the signature of the pipe that runs, `pipe_code` or the method's entry pipe, and
    qualifies a bare pipe code, which the SDK's preparation requires. When the inputs name a local file at a file
    position, `prepare_inputs` uploads it and rewrites it to its `pipelex-storage://` URI; otherwise the inputs go as
    they are. A method whose signature does not resolve is not prepared at all: the run route refuses it, with the
    located diagnostics a preparation error would not carry.

    Raises:
        ApiResponseError: If the hosted API refuses the pipe-io request (an unknown method, a key it refuses).
        InputPreparationError: If an upload fails, or a local file cannot be read.
    """
    if not inputs:
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=None)

    report = await client.pipe_io(PipeIORequest(files=mthds_files, method_ref=method_ref, method_id=method_id, pipe_ref=pipe_code))
    if not isinstance(report, PipeIOValidReport):
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=None)
    selected_pipe_ref = report.pipe_ref
    descriptor = report.input_form.get(selected_pipe_ref) if selected_pipe_ref is not None else None
    if descriptor is None:
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=selected_pipe_ref)

    anchored = anchor_local_file_sources(inputs=inputs, descriptor=descriptor, base_dir=inputs_base_dir)
    if not anchored.local_sources:
        return PreparedHostedInputs(inputs=inputs, uploads=[], pipe_ref=selected_pipe_ref)

    prepared = await client.prepare_inputs(
        files=mthds_files,
        method_ref=method_ref,
        method_id=method_id,
        pipe_ref=selected_pipe_ref,
        inputs=anchored.inputs,
    )
    return PreparedHostedInputs(inputs=prepared.inputs, uploads=prepared.uploads, pipe_ref=selected_pipe_ref)
