"""Client-facing wire records for token usage.

``TokensUsageRecord`` is the wire shape of ``tokens_usages`` on the two client-facing
surfaces: the blocking ``/execute`` response (``pipe_output.tokens_usages``) and the
durable ``tokens_usages.json`` result artifact. The internal runtime models
(``AnyTokensUsage`` and its ``JobMetadata``) never cross the client boundary: the
converter here flattens the kept ``JobMetadata`` fields onto the record and drops the
runtime plumbing (``otel_context``, ``trace_context``, ``session_id``, ``request_id``,
``user_id``, ``pipe_run_id``, ``content_generation_job_id``, ``pipeline_run_id``) and
the rate table (``unit_costs`` — replaced by the computed ``cost``).

The trim happens ONLY at the terminal emission points (the delivery artifact write and
the execute-response dump). Every internal crossing — the runtime-bridge payloads, the
Temporal kajson transport, the usage-event telemetry stream — keeps full-fidelity
records.
"""

from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.usage.cost_registry import compute_tokens_usage_cost
from pipelex.reporting.reporting_types import AnyTokensUsage

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput


class TokensUsageRecord(BaseModel):
    """One client-facing usage record per inference call.

    ``extra="forbid"`` is deliberate: server-side emission is the shape authority, so an
    accidental new field fails loudly here instead of silently widening the contract.
    Enum-ish fields (``model_type``, ``job_category``, ``unit_job_id``, and the
    ``nb_tokens_by_category`` keys) are open sets on the wire, typed as plain strings —
    runtime enum churn is non-breaking for clients.
    """

    model_config = ConfigDict(extra="forbid")

    model_type: str
    inference_model_name: str
    inference_model_id: str
    pipe_code: str | None = None
    job_category: str | None = None
    unit_job_id: str | None = None
    # Raw provider-reported counts: `input` is the joined total; `input_cached` is a
    # subset of it, not additive.
    nb_tokens_by_category: dict[str, int]
    # Computed USD cost of this call; None when the model has no rate table.
    cost: float | None = None
    started_at: str | None = None
    completed_at: str | None = None


def make_tokens_usage_record(tokens_usage: AnyTokensUsage) -> TokensUsageRecord:
    """Convert an internal usage record to its client-facing wire record.

    Flattens the kept ``JobMetadata`` fields (``pipe_code``, job-kind enums, timing)
    onto the record, ISO-dumps the timestamps, and computes ``cost`` from the usage's
    own ``unit_costs`` (which then stay server-side).
    """
    job_metadata = tokens_usage.job_metadata
    return TokensUsageRecord(
        model_type=tokens_usage.model_type,
        inference_model_name=tokens_usage.inference_model_name,
        inference_model_id=tokens_usage.inference_model_id,
        pipe_code=job_metadata.pipe_code,
        job_category=job_metadata.job_category,
        unit_job_id=job_metadata.unit_job_id,
        # TokenCategory is a StrEnum, so the keys ARE strings — the cast just widens the
        # key type for the open-set wire field.
        nb_tokens_by_category=cast("dict[str, int]", dict(tokens_usage.nb_tokens_by_category)),
        cost=compute_tokens_usage_cost(tokens_usage),
        started_at=job_metadata.started_at.isoformat() if job_metadata.started_at else None,
        completed_at=job_metadata.completed_at.isoformat() if job_metadata.completed_at else None,
    )


def dump_tokens_usage_records(tokens_usages: list[AnyTokensUsage] | None) -> list[dict[str, Any]] | None:
    """JSON-safe wire dumps of a run's usage records, preserving the null semantics.

    ``None`` passes through (usage assembly was off for the run), ``[]`` stays ``[]``
    (assembly on, no inference happened).
    """
    if tokens_usages is None:
        return None
    return [make_tokens_usage_record(tokens_usage).model_dump(mode="json") for tokens_usage in tokens_usages]


def apply_tokens_usage_wire_shape(response_dump: dict[str, Any], *, pipe_output: "PipeOutput") -> dict[str, Any]:
    """Replace ``pipe_output.tokens_usages`` in an execute-response dump with wire records.

    Applied by API servers at the terminal emission point, right before the JSON response
    body is built. Deliberately NOT a ``field_serializer``/``model_serializer`` on
    ``PipeOutput``: that model also rides internal transport (kajson over the Temporal
    wire), which must keep full fidelity. Mutates and returns ``response_dump``.
    """
    response_dump["pipe_output"]["tokens_usages"] = dump_tokens_usage_records(pipe_output.tokens_usages)
    return response_dump
