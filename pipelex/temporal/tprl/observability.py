"""Helpers that build the Temporal observability surface (search attributes,
static summary/details, per-activity summary) from Pipelex identity (`PipeJob`,
`JobMetadata`, `PipeAbstract`).

Centralizing the formatting policy keeps the call sites — in
``content_generator_in_workflow.py``, ``temporal_pipe_run.py``,
``temporal_pipe_router.py``, ``wf_pipe_run.py`` — thin and trivially
unit-testable. Length caps follow Temporal's documented limits
(200-byte summary, 20 KB details).
"""

from collections.abc import Mapping
from typing import Final

from temporalio.common import SearchAttributeKey, SearchAttributePair, TypedSearchAttributes

from pipelex.config import get_config
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.temporal_manager import get_temporal_manager

_MAX_SUMMARY_BYTES: Final[int] = 200
_MAX_DETAILS_BYTES: Final[int] = 20 * 1024
_ELLIPSIS: Final[str] = "…"

# Typed search-attribute keys. Defined once at module level so call sites and
# tests can share the exact ``SearchAttributeKey`` instances (key equality is
# by name + type, so identity is not required, but keeping a single instance
# avoids accidental drift between the builder and any future readers).
PIPE_CODE_KEY: Final[SearchAttributeKey[str]] = SearchAttributeKey.for_keyword("PipeCode")
PIPELINE_RUN_ID_KEY: Final[SearchAttributeKey[str]] = SearchAttributeKey.for_keyword("PipelineRunId")
SESSION_ID_KEY: Final[SearchAttributeKey[str]] = SearchAttributeKey.for_keyword("SessionId")
USER_ID_KEY: Final[SearchAttributeKey[str]] = SearchAttributeKey.for_keyword("UserId")
DOMAIN_CODE_KEY: Final[SearchAttributeKey[str]] = SearchAttributeKey.for_keyword("DomainCode")


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Return ``text`` truncated so its UTF-8 encoding fits in ``max_bytes``.

    A trailing ellipsis is appended when truncation occurs. The slice is decoded
    with ``errors="ignore"`` to drop any partial multi-byte sequence at the cut.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    ellipsis_bytes = len(_ELLIPSIS.encode("utf-8"))
    safe = encoded[: max_bytes - ellipsis_bytes].decode("utf-8", errors="ignore")
    return f"{safe}{_ELLIPSIS}"


_LIBRARY_CRATE_ID_LEN: Final[int] = 12


_KEY_BY_NAME: Final[dict[str, SearchAttributeKey[str]]] = {
    "PipeCode": PIPE_CODE_KEY,
    "PipelineRunId": PIPELINE_RUN_ID_KEY,
    "SessionId": SESSION_ID_KEY,
    "UserId": USER_ID_KEY,
    "DomainCode": DOMAIN_CODE_KEY,
}


def stamp_submitter_session_id(pipe_job: PipeJob) -> PipeJob:
    """Stamp the current ``TemporalManager.session_id`` onto ``pipe_job.job_metadata``
    when it is not already set. Called at every top-level Temporal dispatch
    boundary (``TemporalPipeRun.run``, ``TemporalPipeRun.start``,
    ``TemporalPipeRouter._run_pipe_job`` top-level branch) so the value flows
    into child workflows through the workflow input.

    Why this matters: ``build_search_attributes`` reads ``session_id`` off
    ``pipe_job.job_metadata``. Inside workflow code (child-workflow starts in
    ``WfPipeRun`` and ``TemporalPipeRouter``) that read must be deterministic
    — Temporal verifies replayed ``StartChildWorkflowExecution`` commands
    against the recorded ones, and ``TemporalManager.session_id`` differs
    across worker processes. Reading it once at the submitter boundary and
    threading it through the workflow input is the deterministic path.
    """
    if pipe_job.job_metadata.session_id is not None:
        return pipe_job
    stamped_metadata = pipe_job.job_metadata.model_copy(update={"session_id": get_temporal_manager().session_id})
    return pipe_job.model_copy(update={"job_metadata": stamped_metadata})


def build_search_attributes(pipe_job: PipeJob) -> TypedSearchAttributes:
    """Build the typed search attributes for a workflow start, filtered by the
    configured subset.

    Returns an empty ``TypedSearchAttributes`` when
    ``[temporal.search_attributes].enabled = false`` so workflow starts attach
    no custom attributes (the dashboard view degrades to
    WorkflowType / WorkflowId / StartTime). Otherwise emits the subset of pairs
    declared in ``[temporal.search_attributes].attributes``.

    Used identically at top-level dispatch (submitter side) and at child
    dispatch (inside a workflow): the child's ``pipe_job`` already carries the
    inherited ``PipelineRunId`` / ``UserId`` / ``SessionId`` from its parent,
    and ``PipeCode`` / ``DomainCode`` correctly reflect the child's own pipe.
    Reading every field off ``pipe_job`` (the workflow input) keeps the helper
    a pure function — child workflow start commands stay byte-equal across
    replays even when the worker process restarts with a fresh
    ``TemporalManager.session_id``.
    """
    config = get_config().temporal.search_attributes
    if not config.enabled:
        return TypedSearchAttributes([])
    enabled_names = set(config.attributes)
    # ``session_id`` is stamped at the submitter dispatch boundary; if a caller
    # somehow forgot to stamp it, fall back to the empty string so we emit a
    # well-formed (if uninformative) attribute rather than ``None`` — Keyword
    # search attributes don't accept ``None``.
    session_id = pipe_job.job_metadata.session_id or ""
    value_by_name: dict[str, str] = {
        "PipeCode": pipe_job.pipe.code,
        "PipelineRunId": pipe_job.job_metadata.pipeline_run_id,
        "SessionId": session_id,
        "UserId": pipe_job.job_metadata.user_id,
        "DomainCode": pipe_job.pipe.domain_code,
    }
    pairs = [SearchAttributePair(_KEY_BY_NAME[name], value_by_name[name]) for name in _KEY_BY_NAME if name in enabled_names]
    return TypedSearchAttributes(pairs)


def build_static_summary(pipe: PipeAbstract) -> str:
    """Return ``{pipe_code} — {description}`` truncated to 200 bytes.

    ``pipe.description`` is a required-but-can-be-empty Pydantic field; when
    empty the dash-and-tail are omitted entirely.
    """
    if pipe.description:
        text = f"{pipe.code} — {pipe.description}"
    else:
        text = pipe.code
    return _truncate_utf8(text, _MAX_SUMMARY_BYTES)


def build_static_details(pipe_job: PipeJob) -> str:
    """Return a Markdown table of identity fields for the workflow's static details.

    The "Library crate" and "Input" rows are best-effort — emitted when the
    relevant data is available on ``pipe_job``, omitted otherwise.
    """
    pipe = pipe_job.pipe
    metadata = pipe_job.job_metadata
    rows: list[tuple[str, str]] = [
        ("Pipe", f"`{pipe.code}`"),
        ("Domain", f"`{pipe.domain_code}`"),
        ("Pipeline run", f"`{metadata.pipeline_run_id}`"),
        ("User", f"`{metadata.user_id}`"),
        ("Session", f"`{metadata.session_id or ''}`"),
    ]
    if pipe_job.library_crate is not None and pipe_job.library_crate.fingerprint:
        rows.append(("Library crate", f"`{pipe_job.library_crate.fingerprint[:_LIBRARY_CRATE_ID_LEN]}`"))
    input_names = list(pipe.inputs.root.keys())
    if input_names:
        rows.append(("Input", ", ".join(f"`{name}`" for name in input_names)))
    lines: list[str] = ["| Field | Value |", "|---|---|"]
    for field, value in rows:
        lines.append(f"| {field} | {value} |")
    return _truncate_utf8("\n".join(lines), _MAX_DETAILS_BYTES)


def build_activity_summary(
    method_label: str,
    job_metadata: JobMetadata,
    extras: Mapping[str, str] | None = None,
) -> str:
    """Return ``{method_label} · pipe={pipe_code} · {extras...}`` truncated to 200 bytes.

    The ``pipe=`` segment is omitted when ``job_metadata.pipe_code`` is unset so
    the format degrades gracefully for tests / fixtures with no pipe context.

    ``extras`` is a regular mapping (not ``**kwargs``) so callers can use Python
    reserved words as keys — the design table specifies ``class={class_name}``
    verbatim, and ``extras={"class": ...}`` lets the call site stay readable.
    """
    parts: list[str] = [method_label]
    if job_metadata.pipe_code:
        parts.append(f"pipe={job_metadata.pipe_code}")
    if extras:
        for key, value in extras.items():
            parts.append(f"{key}={value}")
    text = " · ".join(parts)
    return _truncate_utf8(text, _MAX_SUMMARY_BYTES)
