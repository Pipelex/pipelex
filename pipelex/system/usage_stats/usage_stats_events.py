"""The events pipelex sends, typed: their properties, the properties every event carries, and the envelope they ride in.

Each model is one event's declared properties and nothing else, `extra="forbid"`, so no property the contract does not
declare can reach a payload. Optional properties are `None` until set and are left out of the payload rather than sent
as `null`. The tests check every event these build against the vendored schema, the same checks PostHog's gate makes.
"""

import math
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from pipelex.system.usage_stats.usage_stats_contract import (
    PERSON_PROFILE_PROPERTY,
    SCHEMA_VERSION,
    TOOL_NAME,
    UsageStatsArch,
    UsageStatsCodegenArtifact,
    UsageStatsCodegenOutcome,
    UsageStatsCodegenTarget,
    UsageStatsErrorDomain,
    UsageStatsEventName,
    UsageStatsHost,
    UsageStatsIntegration,
    UsageStatsMethodSource,
    UsageStatsOs,
    UsageStatsOutcome,
    UsageStatsProvider,
    UsageStatsSurface,
    UsageStatsValidationOutcome,
)

MAX_DURATION_MS = 2_592_000_000
MAX_BUNDLE_SIZE = 100_000
MAX_BUNDLE_DEPTH = 1_000
MAX_PIPE_COUNT = 1_000_000
MAX_MODELS = 10_000
MAX_CALLS = 10_000_000
MAX_TOKENS = 1_000_000_000_000
MAX_IMAGES = 1_000_000
MAX_PAGES = 10_000_000
MAX_COST_USD = 1_000_000.0
MAX_VALIDATION_ITEMS = 100_000


def bounded(*, value: int, maximum: int) -> int:
    """A count held within the contract's bounds, which the gate drops an event for leaving."""
    return max(0, min(value, maximum))


def bounded_duration_ms(*, seconds: float) -> int:
    return bounded(value=round(seconds * 1000), maximum=MAX_DURATION_MS)


def bounded_cost(*, cost_usd: float | None) -> float | None:
    if cost_usd is None or math.isnan(cost_usd):
        return None
    return max(0.0, min(cost_usd, MAX_COST_USD))


class UsageStatsProperties(BaseModel):
    """The base of every event's properties: frozen, and closed to anything the contract does not declare."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class CommonProperties(UsageStatsProperties):
    """The properties every event pipelex sends carries, computed once per process."""

    schema_version: int = Field(default=SCHEMA_VERSION, serialization_alias="schema")
    tool: Literal["pipelex"] = TOOL_NAME
    tool_version: str
    surface: UsageStatsSurface
    integration: UsageStatsIntegration
    host: UsageStatsHost | None = None
    id_new: bool
    os: UsageStatsOs
    arch: UsageStatsArch
    language_runtime: str
    ci: bool
    container: bool
    internal: bool
    notice_version: int


class CommandCompletedProperties(UsageStatsProperties):
    command: str
    outcome: UsageStatsOutcome
    error_domain: UsageStatsErrorDomain | None = None
    duration_ms: int
    hosted: bool | None = None


class BundleShape(UsageStatsProperties):
    """What a bundle declares, described statically: its size and the deepest nesting of its controllers."""

    bundle_pipes: int
    bundle_concepts: int
    bundle_depth: int


class BundleFeatures(UsageStatsProperties):
    feature_batch: bool
    feature_parallel: bool
    feature_condition: bool
    feature_structured_output: bool


class RunCompletedProperties(UsageStatsProperties):
    outcome: UsageStatsOutcome
    error_domain: UsageStatsErrorDomain | None = None
    dry_run: bool
    method_source: UsageStatsMethodSource
    duration_ms: int
    bundle_pipes: int
    bundle_concepts: int
    bundle_depth: int
    feature_batch: bool
    feature_parallel: bool
    feature_condition: bool
    feature_structured_output: bool
    feature_image_input: bool
    feature_document_input: bool
    usage_known: bool
    pipes_llm: int | None = None
    pipes_extract: int | None = None
    pipes_img_gen: int | None = None
    pipes_search: int | None = None
    pipes_compose: int | None = None
    pipes_structure: int | None = None
    pipes_doc_gen: int | None = None
    pipes_judge: int | None = None
    pipes_func: int | None = None
    pipes_sequence: int | None = None
    pipes_parallel: int | None = None
    pipes_condition: int | None = None
    pipes_batch: int | None = None
    pipes_other: int | None = None
    models_used: int | None = None
    inference_calls: int | None = None
    inference_failures: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    images_generated: int | None = None
    pages_extracted: int | None = None
    cost_usd: float | None = None


class ModelUsedProperties(UsageStatsProperties):
    provider: UsageStatsProvider
    model: str
    calls: int
    failures: int
    failures_transient: int
    failures_configuration: int
    failures_content: int
    failures_capacity: int
    failures_ambiguous: int
    failures_unknown: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    images_generated: int
    pages_extracted: int
    cost_usd: float | None = None


class MethodValidatedProperties(UsageStatsProperties):
    outcome: UsageStatsValidationOutcome
    duration_ms: int
    errors: int
    warnings: int
    bundle_pipes: int
    bundle_concepts: int
    bundle_depth: int


class CodeGeneratedProperties(UsageStatsProperties):
    outcome: UsageStatsCodegenOutcome
    artifact: UsageStatsCodegenArtifact
    target: UsageStatsCodegenTarget | None = None
    duration_ms: int
    bundle_pipes: int
    bundle_concepts: int


class UsageStatsEvent(BaseModel):
    """An event as it is created: its name and its own properties. The envelope adds who sent it, and when."""

    model_config = ConfigDict(frozen=True)

    name: UsageStatsEventName
    properties: UsageStatsProperties


def event_timestamp(*, moment: datetime) -> str:
    """RFC 3339 in UTC with milliseconds, such as `2026-10-11T09:30:00.123Z`."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_envelope(*, event: UsageStatsEvent, distinct_id: str, common: CommonProperties) -> dict[str, Any]:
    """The event as it is posted, its `uuid` and `timestamp` fixed now and kept by every resend."""
    properties: dict[str, Any] = {
        **common.model_dump(mode="json", by_alias=True, exclude_none=True),
        **event.properties.model_dump(mode="json", by_alias=True, exclude_none=True),
        PERSON_PROFILE_PROPERTY: False,
    }
    return {
        "event": event.name,
        "distinct_id": distinct_id,
        "uuid": str(uuid4()),
        "timestamp": event_timestamp(moment=datetime.now(UTC)),
        "properties": properties,
    }
