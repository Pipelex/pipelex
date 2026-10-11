"""The usage-statistics events of the method machinery: a run's `run_completed` and `model_used`, `method_validated`
and `code_generated`, built from what the runtime already knows and nothing a user wrote.

Every property is a count, a boolean or a value from a closed list: a bundle is described by how many pipes and
concepts it declares and which language features it uses, never by a name, and a model by the handle a shipped backend
table gives it, or `other`. The contract is `conformance/specs/usage-statistics.md`, "Events".

Building an event never changes the work it describes: nothing is built while statistics are off, and the events go
through the process's client, which owns their delivery.
"""

import re
import time
from collections.abc import Callable, Iterator, Sequence
from functools import cache
from types import TracebackType
from typing import NamedTuple, Self, cast

import tomli

from pipelex import log
from pipelex.base_exceptions import iter_cause_chain
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.cogt.usage.usage_cost import compute_tokens_usage_cost
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.graph.graphspec import GraphSpec
from pipelex.interpreter_hub import get_concept_library
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.usage_stats.usage_stats_client import note_command_error_domain, record_usage_stats_event, usage_stats_are_enabled
from pipelex.system.usage_stats.usage_stats_contract import (
    MODEL_HANDLE_PATTERN,
    OTHER_MODEL,
    UsageStatsCodegenArtifact,
    UsageStatsCodegenOutcome,
    UsageStatsCodegenTarget,
    UsageStatsEventName,
    UsageStatsOutcome,
    UsageStatsProvider,
    UsageStatsValidationOutcome,
)
from pipelex.system.usage_stats.usage_stats_events import (
    MAX_BUNDLE_DEPTH,
    MAX_BUNDLE_SIZE,
    MAX_CALLS,
    MAX_IMAGES,
    MAX_MODELS,
    MAX_PAGES,
    MAX_PIPE_COUNT,
    MAX_TOKENS,
    MAX_VALIDATION_ITEMS,
    BundleShape,
    CodeGeneratedProperties,
    MethodValidatedProperties,
    ModelUsedProperties,
    RunCompletedProperties,
    UsageStatsEvent,
    bounded,
    bounded_cost,
    bounded_duration_ms,
)
from pipelex.system.usage_stats.usage_stats_runs import (
    FAILURE_CATEGORIES,
    RunInferenceTally,
    current_method_source,
    usage_stats_error_domain,
)
from pipelex.tools.log.error_fields import error_fields
from pipelex.tracing.trace_events import PipeStartEvent, TraceEvent, UsageReportEvent

_MODEL_HANDLE = re.compile(MODEL_HANDLE_PATTERN)

#: The `pipes_*` property each pipe type pipelex ships is counted under; any other type is counted under `pipes_other`.
PIPE_TYPE_COUNT_FIELDS: dict[str, str] = {
    "PipeLLM": "pipes_llm",
    "PipeExtract": "pipes_extract",
    "PipeImgGen": "pipes_img_gen",
    "PipeSearch": "pipes_search",
    "PipeCompose": "pipes_compose",
    "PipeStructure": "pipes_structure",
    "PipeDocGen": "pipes_doc_gen",
    "PipeJudge": "pipes_judge",
    "PipeFunc": "pipes_func",
    "PipeSequence": "pipes_sequence",
    "PipeParallel": "pipes_parallel",
    "PipeCondition": "pipes_condition",
    "PipeBatch": "pipes_batch",
}
PIPES_OTHER_FIELD = "pipes_other"
_BATCH_PIPE_TYPE = "PipeBatch"
_PARALLEL_PIPE_TYPE = "PipeParallel"
_CONDITION_PIPE_TYPE = "PipeCondition"
_DEFAULTS_TABLE = "defaults"
_TOML_SUFFIX = ".toml"


# -------------------------------------------------------------------------------------------------
# What a bundle declares
# -------------------------------------------------------------------------------------------------


class BundleFeatureFlags(NamedTuple):
    batch: bool
    parallel: bool
    condition: bool
    structured_output: bool


def _resolver_for(*, pipes: Sequence[PipeAbstract]) -> Callable[..., PipeAbstract | None]:
    """Find a pipe a controller names among the bundle's own pipes: by its domain-qualified ref, or bare in its domain."""
    by_ref: dict[str, PipeAbstract] = {pipe.pipe_ref: pipe for pipe in pipes}

    def resolve(*, pipe_code: str, domain_code: str) -> PipeAbstract | None:
        return by_ref.get(pipe_code) or by_ref.get(f"{domain_code}.{pipe_code}")

    return resolve


def controller_depth(*, pipe: PipeAbstract, pipes: Sequence[PipeAbstract]) -> int:
    """How deeply controllers nest under `pipe`: 0 for an operator, 1 for a controller of operators, and so on.

    A pipe of a dependency package, or one the bundle does not hold, ends the walk, and so does a cycle.
    """
    resolve = _resolver_for(pipes=pipes)
    memo: dict[str, int] = {}

    def depth_of(*, current: PipeAbstract, visiting: frozenset[str]) -> int:
        visit_key = current.visit_key
        if not current.is_controller or visit_key in visiting:
            return 0
        if visit_key in memo:
            return memo[visit_key]
        deepest_child = 0
        for dependency_code in current.pipe_dependencies():
            child = resolve(pipe_code=dependency_code, domain_code=current.domain_code)
            if child is not None:
                deepest_child = max(deepest_child, depth_of(current=child, visiting=visiting | {visit_key}))
        memo[visit_key] = 1 + deepest_child
        return memo[visit_key]

    return depth_of(current=pipe, visiting=frozenset())


def bundle_shape_of(*, pipes: Sequence[PipeAbstract], concepts: Sequence[Concept], main_pipe: PipeAbstract | None) -> BundleShape:
    """The bundle's size and depth: under `main_pipe` for a run, the deepest of all its pipes otherwise."""
    roots = [main_pipe] if main_pipe is not None else list(pipes)
    depth = max((controller_depth(pipe=root, pipes=pipes) for root in roots), default=0)
    return BundleShape(
        bundle_pipes=bounded(value=len(pipes), maximum=MAX_BUNDLE_SIZE),
        bundle_concepts=bounded(value=len(concepts), maximum=MAX_BUNDLE_SIZE),
        bundle_depth=bounded(value=depth, maximum=MAX_BUNDLE_DEPTH),
    )


def is_structured_concept(*, concept: Concept) -> bool:
    """Whether a concept is structured: it declares fields, or its structure is a class of its own rather than a native's.

    A concept that refines another counts as not structured unless it declares fields itself: the walk up its parents
    is the library's to make, and a refinement of a native, the common case, is not structured.
    """
    if concept.declared_structure is not None:
        return True
    if Concept.is_native_concept(concept=concept) or concept.is_described_only:
        return False
    return concept.refines is None


def _batches(*, pipe: PipeAbstract) -> bool:
    if pipe.pipe_type == _BATCH_PIPE_TYPE:
        return True
    if isinstance(pipe, PipeSequence):
        return any(step.batch_params is not None for step in pipe.pipe_steps)
    if isinstance(pipe, PipeParallel):
        return any(sub_pipe.batch_params is not None for sub_pipe in pipe.parallel_sub_pipes)
    return False


def bundle_features_of(*, pipes: Sequence[PipeAbstract]) -> BundleFeatureFlags:
    """Which language features the bundle's pipes use."""
    return BundleFeatureFlags(
        batch=any(_batches(pipe=pipe) for pipe in pipes),
        parallel=any(pipe.pipe_type == _PARALLEL_PIPE_TYPE for pipe in pipes),
        condition=any(pipe.pipe_type == _CONDITION_PIPE_TYPE for pipe in pipes),
        structured_output=any(is_structured_concept(concept=pipe.output.concept) for pipe in pipes),
    )


def _contents_of(*, content: StuffContent) -> Iterator[StuffContent]:
    yield content
    if isinstance(content, ListContent):
        list_content = cast("ListContent[StuffContent]", content)
        for item in list_content.items:
            yield from _contents_of(content=item)


def input_kinds_of(*, working_memory: WorkingMemory | None) -> tuple[bool, bool]:
    """Whether the run's inputs hold an image, and whether they hold a document."""
    if working_memory is None:
        return False, False
    has_image = False
    has_document = False
    for stuff in working_memory.root.values():
        for content in _contents_of(content=stuff.content):
            has_image = has_image or isinstance(content, ImageContent)
            has_document = has_document or isinstance(content, DocumentContent)
    return has_image, has_document


# -------------------------------------------------------------------------------------------------
# Providers and models
# -------------------------------------------------------------------------------------------------


@cache
def shipped_backend_models() -> dict[str, frozenset[str]]:
    """The model names each backend table of this release's kit declares, by backend name."""
    backends_dir = get_kit_configs_dir().joinpath("inference", "backends")
    shipped: dict[str, frozenset[str]] = {}
    for entry in backends_dir.iterdir():
        if not entry.name.endswith(_TOML_SUFFIX):
            continue
        try:
            document = tomli.loads(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomli.TOMLDecodeError):
            continue
        shipped[entry.name.removesuffix(_TOML_SUFFIX)] = frozenset(name for name in document if name != _DEFAULTS_TABLE)
    return shipped


def reported_model(*, provider: UsageStatsProvider, model_handle: str) -> str:
    """The model a `model_used` names: its handle when the release ships it for that provider, `other` otherwise.

    A custom backend's model is always `other`, since its name is the user's.
    """
    if provider.is_custom or _MODEL_HANDLE.fullmatch(model_handle) is None:
        return OTHER_MODEL
    shipped = shipped_backend_models()
    known: bool
    if provider.serves_every_shipped_table:
        known = any(model_handle in models for models in shipped.values())
    else:
        known = model_handle in shipped.get(provider, frozenset())
    return model_handle if known else OTHER_MODEL


# -------------------------------------------------------------------------------------------------
# A run: `run_completed` and `model_used`
# -------------------------------------------------------------------------------------------------


class _ModelUsageRow:
    """What a run did with one reported model, gathered from the tally of its calls and from its usage events."""

    def __init__(self) -> None:
        self.tallied_calls = 0
        self.usage_reports = 0
        self.failures = 0
        self.failures_by_category: dict[str, int] = dict.fromkeys(FAILURE_CATEGORIES, 0)
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.images_generated = 0
        self.pages_extracted = 0
        self.cost_usd = 0.0
        self.is_cost_known = True

    @property
    def calls(self) -> int:
        return max(self.tallied_calls, self.usage_reports)

    @property
    def known_cost(self) -> float | None:
        return self.cost_usd if self.is_cost_known else None


def _model_usage_rows(*, tally: RunInferenceTally | None, events: Sequence[TraceEvent]) -> dict[tuple[UsageStatsProvider, str], _ModelUsageRow]:
    """The run's models as `model_used` reports them, merged by provider and reported model."""
    rows: dict[tuple[UsageStatsProvider, str], _ModelUsageRow] = {}

    def row_for(*, model_handle: str, backend_name: str | None) -> _ModelUsageRow:
        provider = UsageStatsProvider.for_backend(backend_name=backend_name)
        key = (provider, reported_model(provider=provider, model_handle=model_handle))
        if key not in rows:
            rows[key] = _ModelUsageRow()
        return rows[key]

    if tally is not None:
        for (tallied_handle, tallied_backend), model_tally in tally.models.items():
            row = row_for(model_handle=tallied_handle, backend_name=tallied_backend)
            row.tallied_calls += model_tally.calls
            row.failures += model_tally.failures
            for category, count in model_tally.failures_by_category.items():
                row.failures_by_category[category] += count
            row.images_generated += model_tally.images_generated
            row.pages_extracted += model_tally.pages_extracted

    for event in events:
        if not isinstance(event, UsageReportEvent):
            continue
        tokens_usage = event.tokens_usage
        model_handle = tokens_usage.inference_model_name
        reporting_backend = (
            tally.backend_for_usage(model_handle=model_handle, model_id=tokens_usage.inference_model_id) if tally is not None else None
        )
        row = row_for(model_handle=model_handle, backend_name=reporting_backend)
        row.usage_reports += 1
        if tokens_usage.pricing_unit.counts_tokens:
            nb_tokens_by_category = tokens_usage.nb_tokens_by_category
            row.input_tokens += nb_tokens_by_category.get(TokenCategory.INPUT, 0)
            row.output_tokens += nb_tokens_by_category.get(TokenCategory.OUTPUT, 0)
            row.cached_tokens += nb_tokens_by_category.get(TokenCategory.INPUT_CACHED, 0)
        cost = compute_tokens_usage_cost(tokens_usage)
        if cost is None:
            row.is_cost_known = False
        else:
            row.cost_usd += cost
    return rows


def count_pipe_types(*, pipe_types: Sequence[str]) -> dict[str, int]:
    """Every `pipes_*` count, zero included, of the pipe types a run executed."""
    counts: dict[str, int] = dict.fromkeys([*PIPE_TYPE_COUNT_FIELDS.values(), PIPES_OTHER_FIELD], 0)
    for pipe_type in pipe_types:
        counts[PIPE_TYPE_COUNT_FIELDS.get(pipe_type, PIPES_OTHER_FIELD)] += 1
    return {field: bounded(value=count, maximum=MAX_PIPE_COUNT) for field, count in counts.items()}


def executed_pipe_types(*, events: Sequence[TraceEvent], closed_graph: GraphSpec | None) -> list[str]:
    """The types of the pipes a run executed: from its pipe-start events, or from its tracer's graph when it wrote none.

    A run reporting its costs without its graph writes no pipe-start event, while its tracer still drew the graph in memory.
    """
    started = [event.pipe_type for event in events if isinstance(event, PipeStartEvent)]
    if started or closed_graph is None:
        return started
    return [node.pipe_type for node in closed_graph.nodes if node.pipe_type]


class RunUsageFacts(NamedTuple):
    """What a run's end knows that its `run_completed` describes."""

    outcome: UsageStatsOutcome
    error: BaseException | None
    is_dry_run: bool
    duration_seconds: float
    main_pipe: PipeAbstract
    own_pipes: Sequence[PipeAbstract]
    own_concepts: Sequence[Concept]
    has_image_input: bool
    has_document_input: bool
    events: Sequence[TraceEvent] | None
    closed_graph: GraphSpec | None
    tally: RunInferenceTally | None


def build_run_usage_events(*, facts: RunUsageFacts) -> list[UsageStatsEvent]:
    """The run's `run_completed`, then one `model_used` per model when its events were read."""
    shape = bundle_shape_of(pipes=facts.own_pipes, concepts=facts.own_concepts, main_pipe=facts.main_pipe)
    features = bundle_features_of(pipes=facts.own_pipes)
    is_usage_known = facts.events is not None
    run_properties = RunCompletedProperties(
        outcome=facts.outcome,
        error_domain=usage_stats_error_domain(error=facts.error) if facts.outcome.is_failed else None,
        dry_run=facts.is_dry_run,
        method_source=current_method_source(),
        duration_ms=bounded_duration_ms(seconds=facts.duration_seconds),
        bundle_pipes=shape.bundle_pipes,
        bundle_concepts=shape.bundle_concepts,
        bundle_depth=shape.bundle_depth,
        feature_batch=features.batch,
        feature_parallel=features.parallel,
        feature_condition=features.condition,
        feature_structured_output=features.structured_output,
        feature_image_input=facts.has_image_input,
        feature_document_input=facts.has_document_input,
        usage_known=is_usage_known,
    )
    if facts.events is None:
        return [UsageStatsEvent(name=UsageStatsEventName.RUN_COMPLETED, properties=run_properties)]

    rows = _model_usage_rows(tally=facts.tally, events=facts.events)
    model_costs = [row.known_cost for row in rows.values()]
    run_cost: float | None = None if any(cost is None for cost in model_costs) else sum(cost for cost in model_costs if cost is not None)
    tallied_calls = facts.tally.calls if facts.tally is not None else 0
    tallied_failures = facts.tally.failures if facts.tally is not None else 0
    pipe_counts = count_pipe_types(pipe_types=executed_pipe_types(events=facts.events, closed_graph=facts.closed_graph))
    run_properties = run_properties.model_copy(
        update={
            **pipe_counts,
            "models_used": bounded(value=len(rows), maximum=MAX_MODELS),
            "inference_calls": bounded(value=max(tallied_calls, sum(row.calls for row in rows.values())), maximum=MAX_CALLS),
            "inference_failures": bounded(value=tallied_failures, maximum=MAX_CALLS),
            "input_tokens": bounded(value=sum(row.input_tokens for row in rows.values()), maximum=MAX_TOKENS),
            "output_tokens": bounded(value=sum(row.output_tokens for row in rows.values()), maximum=MAX_TOKENS),
            "cached_tokens": bounded(value=sum(row.cached_tokens for row in rows.values()), maximum=MAX_TOKENS),
            "images_generated": bounded(value=sum(row.images_generated for row in rows.values()), maximum=MAX_IMAGES),
            "pages_extracted": bounded(value=sum(row.pages_extracted for row in rows.values()), maximum=MAX_PAGES),
            "cost_usd": bounded_cost(cost_usd=run_cost),
        }
    )
    # Validated again: `model_copy` does not validate the counts it sets.
    usage_events = [
        UsageStatsEvent(name=UsageStatsEventName.RUN_COMPLETED, properties=RunCompletedProperties.model_validate(run_properties.model_dump()))
    ]
    for (provider, model), row in rows.items():
        usage_events.append(
            UsageStatsEvent(
                name=UsageStatsEventName.MODEL_USED,
                properties=ModelUsedProperties(
                    provider=provider,
                    model=model,
                    calls=bounded(value=row.calls, maximum=MAX_CALLS),
                    failures=bounded(value=row.failures, maximum=MAX_CALLS),
                    failures_transient=bounded(value=row.failures_by_category["transient"], maximum=MAX_CALLS),
                    failures_configuration=bounded(value=row.failures_by_category["configuration"], maximum=MAX_CALLS),
                    failures_content=bounded(value=row.failures_by_category["content"], maximum=MAX_CALLS),
                    failures_capacity=bounded(value=row.failures_by_category["capacity"], maximum=MAX_CALLS),
                    failures_ambiguous=bounded(value=row.failures_by_category["ambiguous"], maximum=MAX_CALLS),
                    failures_unknown=bounded(value=row.failures_by_category["unknown"], maximum=MAX_CALLS),
                    input_tokens=bounded(value=row.input_tokens, maximum=MAX_TOKENS),
                    output_tokens=bounded(value=row.output_tokens, maximum=MAX_TOKENS),
                    cached_tokens=bounded(value=row.cached_tokens, maximum=MAX_TOKENS),
                    images_generated=bounded(value=row.images_generated, maximum=MAX_IMAGES),
                    pages_extracted=bounded(value=row.pages_extracted, maximum=MAX_PAGES),
                    cost_usd=bounded_cost(cost_usd=row.known_cost),
                ),
            )
        )
    return usage_events


def report_run_usage(*, facts: RunUsageFacts) -> None:
    """Record a run's `run_completed` and `model_used` events, and its error domain for the command that ran it."""
    usage_events = build_run_usage_events(facts=facts)
    if facts.outcome.is_failed:
        note_command_error_domain(error_domain=usage_stats_error_domain(error=facts.error))
    for usage_event in usage_events:
        record_usage_stats_event(event=usage_event)


# -------------------------------------------------------------------------------------------------
# A validation: `method_validated`
# -------------------------------------------------------------------------------------------------


def _find_validate_bundle_error(*, error: BaseException | None) -> ValidateBundleError | None:
    """The invalid verdict an error carries, raised itself or handled on the way to it (a CLI's exit after rendering it)."""
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for node in iter_cause_chain(current):
            if isinstance(node, ValidateBundleError):
                return node
        current = current.__context__
    return None


class MethodValidationReport:
    """Times one validation of a method and records its `method_validated` when it ends, however it ends.

    A context manager around the validation. Its verdict is read off the way the block ends: an invalid verdict when a
    `ValidateBundleError` raised in it, or handled on the way to the exception leaving it; `failed` for any other
    exception, unless the block declared the verdict valid first (a valid library refused for its pending signatures
    is valid); `valid` otherwise. The block describes the bundle as soon as it knows it.
    """

    def __init__(self) -> None:
        self._started_at = 0.0
        self._pipes: Sequence[PipeAbstract] = ()
        self._concepts: Sequence[Concept] = ()
        self._warnings = 0
        self._is_declared_valid = False
        self._could_not_describe = False

    def __enter__(self) -> Self:
        self._started_at = time.monotonic()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if not usage_stats_are_enabled():
            return
        try:
            self._record(exc_value=exc_value)
        except (ValueError, OSError) as report_error:
            # An event that will not validate, a state that cannot be read: a statistic that cannot be built is lost,
            # and it never replaces the verdict it describes.
            log.debug("A usage statistics event could not be built", fields=error_fields(exc=report_error))

    def _record(self, *, exc_value: BaseException | None) -> None:
        if self._could_not_describe:
            # A bundle the report could not describe would be counted wrong: the event is lost instead.
            return
        outcome: UsageStatsValidationOutcome
        errors = 0
        invalid_verdict = _find_validate_bundle_error(error=exc_value)
        if invalid_verdict is not None:
            outcome = UsageStatsValidationOutcome.INVALID
            errors = max(1, len(invalid_verdict.validation_error_items()))
        elif exc_value is None or self._is_declared_valid:
            outcome = UsageStatsValidationOutcome.VALID
        else:
            outcome = UsageStatsValidationOutcome.FAILED
        shape = bundle_shape_of(pipes=self._pipes, concepts=self._concepts, main_pipe=None)
        record_usage_stats_event(
            event=UsageStatsEvent(
                name=UsageStatsEventName.METHOD_VALIDATED,
                properties=MethodValidatedProperties(
                    outcome=outcome,
                    duration_ms=bounded_duration_ms(seconds=time.monotonic() - self._started_at),
                    errors=bounded(value=errors, maximum=MAX_VALIDATION_ITEMS),
                    warnings=bounded(value=self._warnings, maximum=MAX_VALIDATION_ITEMS),
                    bundle_pipes=shape.bundle_pipes,
                    bundle_concepts=shape.bundle_concepts,
                    bundle_depth=shape.bundle_depth,
                ),
            )
        )

    def describe(self, *, pipes: Sequence[PipeAbstract]) -> None:
        """Describe the validated bundle by its pipes and by the concepts of the library it loaded, which must be current."""
        if not usage_stats_are_enabled():
            return
        try:
            self._pipes = list(pipes)
            self._concepts = get_concept_library().list_own_concepts()
        except (RuntimeError, LibraryError) as describe_error:
            # No interpreter hub or no library manager set up (`RuntimeError`), or no current library (`LibraryError`):
            # describing the bundle for a statistic must never break the validation itself.
            self._could_not_describe = True
            log.debug("A validated bundle could not be described for usage statistics", fields=error_fields(exc=describe_error))

    def count_warnings(self, *, count: int) -> None:
        self._warnings += count

    def declare_valid(self) -> None:
        """Declare the verdict valid, so a refusal the block raises next for another reason does not read as a failure."""
        self._is_declared_valid = True


# -------------------------------------------------------------------------------------------------
# A code generation: `code_generated`
# -------------------------------------------------------------------------------------------------


def usage_stats_codegen_target(*, target: str) -> UsageStatsCodegenTarget:
    """The target flavour a `code_generated` names: the codegen target itself, which the contract lists, or `other`."""
    try:
        return UsageStatsCodegenTarget(target)
    except ValueError:
        return UsageStatsCodegenTarget.OTHER


class CodeGenerationReport:
    """Times one code generation and records its `code_generated` when it ends.

    A context manager around the generation, the load of its library included. It succeeded unless an exception leaves
    the block, or unless the block declared the outcome first: a surface that answers a failure without raising, an
    API's invalid verdict, declares it failed, and one that leaves by an exception after a generation with nothing to
    generate declares it succeeded.
    """

    def __init__(self, *, artifact: UsageStatsCodegenArtifact, target: UsageStatsCodegenTarget | None = None) -> None:
        self._artifact = artifact
        self._target = target
        self._started_at = 0.0
        self._pipes = 0
        self._concepts = 0
        self._declared_outcome: UsageStatsCodegenOutcome | None = None

    @property
    def artifact(self) -> UsageStatsCodegenArtifact:
        """What the generation produces, as its `code_generated` reports it."""
        return self._artifact

    def __enter__(self) -> Self:
        self._started_at = time.monotonic()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if not usage_stats_are_enabled():
            return
        try:
            self._record(exc_value=exc_value)
        except (ValueError, OSError) as report_error:
            # A statistic that cannot be built is lost; it never replaces the outcome of the work it describes.
            log.debug("A usage statistics event could not be built", fields=error_fields(exc=report_error))

    def _record(self, *, exc_value: BaseException | None) -> None:
        target = self._target
        if self._artifact.has_target and target is None:
            target = UsageStatsCodegenTarget.OTHER
        outcome = self._declared_outcome
        if outcome is None:
            outcome = UsageStatsCodegenOutcome.SUCCEEDED if exc_value is None else UsageStatsCodegenOutcome.FAILED
        record_usage_stats_event(
            event=UsageStatsEvent(
                name=UsageStatsEventName.CODE_GENERATED,
                properties=CodeGeneratedProperties(
                    outcome=outcome,
                    artifact=self._artifact,
                    target=target if self._artifact.has_target else None,
                    duration_ms=bounded_duration_ms(seconds=time.monotonic() - self._started_at),
                    bundle_pipes=bounded(value=self._pipes, maximum=MAX_BUNDLE_SIZE),
                    bundle_concepts=bounded(value=self._concepts, maximum=MAX_BUNDLE_SIZE),
                ),
            )
        )

    def describe(self, *, crate: LibraryCrate) -> None:
        """Describe the library generated from by the size of its crate, which the event counts."""
        self._pipes = len(crate.pipes)
        self._concepts = len(crate.concepts)

    def declare_failed(self) -> None:
        self._declared_outcome = UsageStatsCodegenOutcome.FAILED

    def declare_succeeded(self) -> None:
        self._declared_outcome = UsageStatsCodegenOutcome.SUCCEEDED
