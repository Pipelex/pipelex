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

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.temporal_manager import get_temporal_manager

_MAX_SUMMARY_BYTES: Final[int] = 200
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


def build_search_attributes(pipe_job: PipeJob) -> TypedSearchAttributes:
    """Build the five-keyed typed search attributes for a workflow start.

    Used identically at top-level dispatch (submitter side) and at child dispatch
    (inside a workflow): the child's ``pipe_job`` already carries the inherited
    ``PipelineRunId`` / ``UserId`` from its parent, and ``PipeCode`` /
    ``DomainCode`` correctly reflect the child's own pipe.
    """
    return TypedSearchAttributes(
        [
            SearchAttributePair(PIPE_CODE_KEY, pipe_job.pipe.code),
            SearchAttributePair(PIPELINE_RUN_ID_KEY, pipe_job.job_metadata.pipeline_run_id),
            SearchAttributePair(SESSION_ID_KEY, get_temporal_manager().session_id),
            SearchAttributePair(USER_ID_KEY, pipe_job.job_metadata.user_id),
            SearchAttributePair(DOMAIN_CODE_KEY, pipe_job.pipe.domain_code),
        ],
    )


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
        ("Session", f"`{get_temporal_manager().session_id}`"),
    ]
    if pipe_job.library_crate is not None and pipe_job.library_crate.fingerprint:
        rows.append(("Library crate", f"`{pipe_job.library_crate.fingerprint[:_LIBRARY_CRATE_ID_LEN]}`"))
    input_names = list(pipe.inputs.root.keys())
    if input_names:
        rows.append(("Input", ", ".join(f"`{name}`" for name in input_names)))
    lines: list[str] = ["| Field | Value |", "|---|---|"]
    for field, value in rows:
        lines.append(f"| {field} | {value} |")
    return "\n".join(lines)


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
