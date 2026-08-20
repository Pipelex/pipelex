"""Leaf-level inference mocking for ``--dry-run`` (``run_mode=DRY``).

One non-live mode, one mechanism. The dry run fakes the AI call *at the cogt
leaf* — the lowest point where ``ContentGenerator`` (direct, inline) and the
Temporal activities (``act_llm_gen_*`` and friends) converge — so a single
branch covers both backends and ``run_mode`` stays orthogonal to backend choice
(D-plan §3.5). ``CogtRunParams.run_mode == DRY`` rides every assignment; the
leaf routes to the :func:`dry_llm_gen_text` / :func:`dry_llm_gen_object` / ...
helpers here. Non-LLM dry leaves (img-gen / extract / render / search /
templating) mint synthetic outputs without reporting usage. For img-gen and
extract, the DRY branch lives at the ``*_and_store`` layer — one step above the
raw provider leaf — so a dry run performs **no storage IO** (eng review D10).

Usage reporting is keyed on the internal ``CogtRunParams.is_mock_usage``
sub-flag (DRY-only; the only CLI access is the hidden ``--mock-usage`` test
trigger, which requires ``--dry-run`` and is not shown in --help):

- ``is_mock_usage=False`` (default): the LLM leaves report a **zero-token**
  synthetic job via :func:`report_dry_llm_job`. Zero tokens ⇒
  ``AggregatedCosts.has_reportable_usage`` is False ⇒ the end-of-run cost report
  is suppressed (correct: a dry run did no real work).
- ``is_mock_usage=True``: the LLM leaves report **non-zero** synthetic usage via
  :func:`report_mock_usage_llm_job`. Non-zero tokens ⇒ a cost report *renders*.
  Only a non-zero mock can validate cross-worker cost-report rendering cheaply
  and deterministically (no provider spend) — that is this flag's whole reason
  to exist. Non-LLM leaves keep their no-usage dry behavior either way.

This module is the single home for "what a mocked inference produces". Object
mocks resolve their class exactly the way the live leaf does (see
``object_class_resolution``): from the caller's real class when one is in hand,
from the JSON schema otherwise — so the mock is never built against a *weaker*
class than the one the provider is constrained by. Exotic format constraints
must declare ``examples`` / ``mock_format`` — see ``DryRunObjectFidelityError``.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError
from pydantic.errors import PydanticInvalidForJsonSchema

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    LLMAssignment,
    ObjectAssignment,
    RenderPageViewsAssignment,
    SearchAssignment,
    SearchObjectAssignment,
    TemplatingAssignment,
)
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.content_generation.exceptions import DryRunMockBuildError, OutputStructureSchemaError
from pipelex.cogt.content_generation.object_class_resolution import resolve_object_class
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.runtime_hub import get_report_delegate
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

# The pipe code every mocked bundle answers to — shared with BundleHeaderSpec.main_pipe's
# examples so bundle dry-validation's mocked header names a pipe that exists (D3).
MOCK_MAIN_PIPE_CODE = "mock_main"

# Sentinel model identifiers so a synthetic usage record is never confused with real inference.
DRY_RUN_INFERENCE_MODEL_NAME = "dry_run"
DRY_RUN_INFERENCE_MODEL_ID = "dry_run"
MOCK_USAGE_MODEL_NAME = "mock_usage"
MOCK_USAGE_MODEL_ID = "mock_usage"

# Synthetic, deterministic, clearly non-real token counts for ``is_mock_usage=True``. Non-zero so the
# assembled usage is reportable (``AggregatedCosts.has_reportable_usage`` True → the cost report renders),
# which is exactly what the default dry run's zero-token usage deliberately suppresses. Input/output
# differ so the rendered table distinguishes the two columns. Cost stays 0 (``unit_costs={}``): a mocked
# run has token usage but no real spend — the "free model" reporting case.
MOCK_USAGE_NB_TOKENS_BY_CATEGORY: NbTokensByCategoryDict = {
    TokenCategory.INPUT: 100,
    TokenCategory.OUTPUT: 50,
}


def _report_synthetic_llm_job(
    *,
    job_metadata: JobMetadata,
    llm_setting: LLMSetting,
    llm_prompt: LLMPrompt,
    inference_model_name: str,
    inference_model_id: str,
    nb_tokens_by_category: NbTokensByCategoryDict,
) -> None:
    """Build a synthetic ``LLMJob`` and report it through ``get_report_delegate()``.

    Shared core of :func:`report_dry_llm_job` (zero tokens) and
    :func:`report_mock_usage_llm_job` (non-zero tokens). Reporting it makes the runner-side
    cross-worker emission path observable without a real LLM call.

    The synthetic ``job_metadata`` copy gets ``completed_at`` set so ``report_inference_job`` can
    format the duration without crashing on ``None`` — matching what ``LLMJob.llm_job_after_complete``
    does in the live path. ``JobMetadata.started_at`` can arrive either offset-naive (from the default
    factory) or offset-aware (e.g. ``pipe_abstract.py`` uses ``datetime.now(timezone.utc)``), so the
    synthetic ``now`` is built with the same tzinfo as the incoming ``started_at`` — mixing aware/naive
    raises ``TypeError`` when ``JobMetadata.duration`` subtracts.
    """
    tz = job_metadata.started_at.tzinfo if job_metadata.started_at is not None else None
    now = datetime.now(tz)
    synthetic_metadata = job_metadata.model_copy(
        update={
            "started_at": job_metadata.started_at or now,
            "completed_at": now,
        },
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=synthetic_metadata,
        inference_model_name=inference_model_name,
        inference_model_id=inference_model_id,
        unit_costs={},
        nb_tokens_by_category=nb_tokens_by_category,
    )
    synthetic_job = LLMJob(
        job_metadata=synthetic_metadata,
        llm_prompt=llm_prompt,
        job_params=llm_setting.make_llm_job_params(),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )
    get_report_delegate().report_inference_job(inference_job=synthetic_job)


def report_dry_llm_job(job_metadata: JobMetadata, *, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None:
    """Report a zero-token synthetic LLM job for a ``--dry-run`` inference (cost report suppressed)."""
    _report_synthetic_llm_job(
        job_metadata=job_metadata,
        llm_setting=llm_setting,
        llm_prompt=llm_prompt,
        inference_model_name=DRY_RUN_INFERENCE_MODEL_NAME,
        inference_model_id=DRY_RUN_INFERENCE_MODEL_ID,
        nb_tokens_by_category={},
    )


def report_mock_usage_llm_job(job_metadata: JobMetadata, *, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None:
    """Report a non-zero synthetic LLM job for a dry run with ``is_mock_usage=True`` (cost report renders)."""
    _report_synthetic_llm_job(
        job_metadata=job_metadata,
        llm_setting=llm_setting,
        llm_prompt=llm_prompt,
        inference_model_name=MOCK_USAGE_MODEL_NAME,
        inference_model_id=MOCK_USAGE_MODEL_ID,
        nb_tokens_by_category=dict(MOCK_USAGE_NB_TOKENS_BY_CATEGORY),
    )


def build_mock_object(model_class: type[BaseModelTypeVar], **field_values: Any) -> BaseModelTypeVar:
    """Build one mock instance of ``model_class`` via the dry-run polyfactory.

    Runs validators so the mock is valid; fields with format constraints
    (snake_case, PascalCase, ...) should declare ``examples`` / ``mock_format`` so
    polyfactory uses those instead of random strings. ``field_values`` pin specific
    fields instead of generating them.

    A build failure is deterministic (retries can never succeed), so it is wrapped
    into the typed :class:`DryRunMockBuildError` naming the class and the remedy;
    the activity error boundary then makes it terminal (eng review D7, listed in
    ``non_retryable_error_types``).
    """
    try:
        return DryRunFactory.make_dry_run_factory(model_class).build(**field_values)
    except (ValidationError, FactoryException) as exc:
        raise DryRunMockBuildError.for_object_class(model_class.__name__) from exc


def build_mock_objects(model_class: type[BaseModelTypeVar], *, count: int) -> list[BaseModelTypeVar]:
    """Build ``count`` mock instances with a single factory construction.

    ``DryRunFactory.make_dry_run_factory`` recursively scans the model tree and mints dynamic
    factory classes — building it once per list (not once per item) keeps list mocks linear in
    item construction only. Same :class:`DryRunMockBuildError` wrap as :func:`build_mock_object`.
    """
    factory = DryRunFactory.make_dry_run_factory(model_class)
    try:
        return [factory.build() for _ in range(count)]
    except (ValidationError, FactoryException) as exc:
        raise DryRunMockBuildError.for_object_class(model_class.__name__) from exc


def stamp_mock_main_coordination(items: Sequence[Any]) -> None:
    """Set the first item's ``pipe_code`` to ``"mock_main"`` — the single home of this coordination (D3).

    WHY: bundle dry-validation mocks a ``BundleHeaderSpec`` whose ``main_pipe`` field declares
    ``examples=["mock_main"]`` (``pipelex/builder/bundle_header_spec.py``), so the polyfactory mock
    header names ``mock_main`` as the bundle's main pipe. Every mock that fabricates a *list of pipe
    specs* must therefore make its first item answer to that name, or the mocked bundle fails its own
    main-pipe check. Callers: the mock-input factory (``working_memory_factory``), the batch
    controller's dry aggregation (``pipe_batch``), and the dry object-list leaf mock
    (:func:`dry_llm_gen_object_list`). The stamp is a no-op for items without a ``pipe_code`` field.

    The item is now the *caller's own* class, not a throwaway schema rebuild, so the assignment can hit
    a model config the caller chose — ``frozen=True`` or ``validate_assignment`` — and raise. Surface
    that as the same typed :class:`DryRunMockBuildError` the surrounding mock build uses, rather than
    letting a raw ``ValidationError`` escape from a mutation the caller never asked for.
    """
    if items and hasattr(items[0], "pipe_code"):
        try:
            items[0].pipe_code = MOCK_MAIN_PIPE_CODE
        except ValidationError as exc:
            raise DryRunMockBuildError.for_object_class(type(items[0]).__name__) from exc


def _nb_list_items(object_assignment: ObjectAssignment) -> int:
    """Resolve the object-list mock length: the assignment's fixed ``nb_items`` wins (D11), including 0."""
    if object_assignment.nb_items is not None:
        return object_assignment.nb_items
    return get_config().inference.dry_run.nb_list_items


class _ReportLLMJobFunc(Protocol):
    def __call__(self, job_metadata: JobMetadata, *, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None: ...


def _leaf_gen_object(object_assignment: ObjectAssignment, *, report_func: _ReportLLMJobFunc, object_class: type[BaseModel] | None) -> BaseModel:
    """Shared object-mock pipeline: resolve the class to mock, report once, build one mock.

    With the caller's class in hand the mock is built from it directly, so every invariant it enforces
    is honored. Without it (the boundary case) the class is rebuilt from the JSON schema, which drops
    custom validators and the format hints encoded via ``json_schema_extra`` that
    datamodel-code-generator omits on round-trip — so exotic-format schemas may yield mock data the
    original class would reject. The generator re-validates against the original class and re-raises
    that failure as ``DryRunObjectFidelityError`` (review F2); declare ``examples`` / ``mock_format``
    on the constrained fields to fix it.

    Reports exactly once — the live leaf makes one ``gen_object`` call (a list is one call against a
    list-wrapper schema), so a single ``UsageReportEvent`` matches the real one-call topology that
    cross-worker assertions count.
    """
    item_class = resolve_object_class(object_assignment=object_assignment, object_class=object_class)
    mock_object = build_mock_object(item_class)
    # Report only after a successful build — a failed mock must not leave a usage event behind.
    llm_assignment = object_assignment.llm_assignment_for_object
    report_func(llm_assignment.job_metadata, llm_setting=llm_assignment.llm_setting, llm_prompt=llm_assignment.llm_prompt)
    return mock_object


def _leaf_gen_object_list(
    object_assignment: ObjectAssignment, *, report_func: _ReportLLMJobFunc, object_class: type[BaseModel] | None
) -> list[BaseModel]:
    """List counterpart of :func:`_leaf_gen_object`: one report, ``nb_items`` builds (D11)."""
    item_class = resolve_object_class(object_assignment=object_assignment, object_class=object_class)
    mock_objects = build_mock_objects(item_class, count=_nb_list_items(object_assignment))
    # Report only after a successful build — a failed mock must not leave a usage event behind.
    llm_assignment = object_assignment.llm_assignment_for_object
    report_func(llm_assignment.job_metadata, llm_setting=llm_assignment.llm_setting, llm_prompt=llm_assignment.llm_prompt)
    return mock_objects


# --- Dry leaf helpers (``run_mode == DRY``) -------------------------------------------------------
#
# Each helper mints the synthetic output for one leaf, so a dry run behaves identically inline
# (direct backend) and inside a Temporal activity (the backend dispatches normally; the leaf mocks).


def _dry_report_func(cogt_run_params: CogtRunParams) -> _ReportLLMJobFunc:
    """Select the synthetic-job report func for a dry LLM leaf on the ``is_mock_usage`` sub-flag.

    Default: zero-token (cost report suppressed). ``is_mock_usage=True``: non-zero sentinel counts
    (cost report renders) — the cross-worker cost-report validation affordance.
    """
    if cogt_run_params.is_mock_usage:
        return report_mock_usage_llm_job
    return report_dry_llm_job


def _dry_text_gen_truncate_length() -> int:
    return get_config().inference.dry_run.text_gen_truncate_length


def dry_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    """Dry leaf for ``llm_gen_text``: synthetic job report + a ``DRY RUN:`` marker string."""
    job_metadata = llm_assignment.job_metadata
    log.verbose(f"🤡 DRY RUN: llm_gen_text for '{job_metadata.run_metadata.pipeline_run_id}'")
    report_func = _dry_report_func(llm_assignment.cogt_run_params)
    report_func(job_metadata, llm_setting=llm_assignment.llm_setting, llm_prompt=llm_assignment.llm_prompt)
    prompt_truncated = llm_assignment.llm_prompt.desc(truncate_text_length=_dry_text_gen_truncate_length())
    return f"DRY RUN: llm_gen_text • llm_setting={llm_assignment.llm_setting.desc()} • prompt={prompt_truncated}"


def dry_llm_gen_object(object_assignment: ObjectAssignment, *, object_class: type[BaseModel] | None = None) -> BaseModel:
    """Dry leaf for ``llm_gen_object``: mock instance + synthetic job report.

    Mirrors the live leaf's class resolution so the two run modes cannot drift: with the caller's class
    in hand the mock is built from it, without it the class is rebuilt from the schema.
    """
    log.verbose(f"🤡 DRY RUN: llm_gen_object for '{object_assignment.object_class_name}'")
    return _leaf_gen_object(object_assignment, report_func=_dry_report_func(object_assignment.cogt_run_params), object_class=object_class)


def dry_llm_gen_object_list(object_assignment: ObjectAssignment, *, object_class: type[BaseModel] | None = None) -> list[BaseModel]:
    """Dry leaf for ``llm_gen_object_list``: ``nb_items`` mocks + one synthetic report.

    Applies :func:`stamp_mock_main_coordination` so bundle dry-validation's mocked
    ``BundleHeaderSpec.main_pipe`` check passes through the leaf mock (D3). The stamp is
    unconditional on ``is_mock_usage`` — it only matters to bundle dry-validation and is
    harmless elsewhere.
    """
    log.verbose(f"🤡 DRY RUN: llm_gen_object_list for '{object_assignment.object_class_name}'")
    items = _leaf_gen_object_list(object_assignment, report_func=_dry_report_func(object_assignment.cogt_run_params), object_class=object_class)
    stamp_mock_main_coordination(items)
    return items


def dry_templating_gen_text(templating_assignment: TemplatingAssignment) -> str:
    """Dry leaf for ``templating_gen_text``: parse-check the template (a bad jinja2 template must
    still fail under DRY), then return a marker string instead of rendering.
    """
    check_jinja2_parsing(
        template_source=templating_assignment.template,
        template_category=templating_assignment.category,
    )
    log.verbose("🤡 DRY RUN: templating_gen_text")
    jinja2_truncated = templating_assignment.template[: _dry_text_gen_truncate_length()]
    # Context KEYS only: the context is built from working memory, so dumping values would leak
    # inputs the real template never renders (and bloat the mock output).
    context_keys = sorted(templating_assignment.context.keys())
    return (
        f"DRY RUN: templating_gen_text • context_keys={context_keys} • "
        f"jinja2={jinja2_truncated} • templating_style={templating_assignment.templating_style} • "
        f"template_category={templating_assignment.category}"
    )


def _dry_image_content(image_url: str, *, img_gen_assignment: ImgGenAssignment | None = None) -> ImageContent:
    image_content = ImageContent(
        url=image_url,
        public_url=image_url,
        mime_type="image/jpeg",
        width=1024,
        height=1024,
    )
    if img_gen_assignment:
        image_content.source_prompt = img_gen_assignment.img_gen_prompt.positive_text
        image_content.source_negative_prompt = img_gen_assignment.img_gen_prompt.negative_text
    return image_content


def dry_img_gen_image_contents(img_gen_assignment: ImgGenAssignment) -> list[ImageContent]:
    """Dry leaf for image generation: URL-only ``ImageContent`` mocks, no provider, no storage IO.

    Sits at the ``*_and_store`` layer — one step above the raw provider leaf — so a dry run never
    touches the storage provider (eng review D10).
    """
    log.verbose(f"🤡 DRY RUN: img_gen for '{img_gen_assignment.img_gen_handle}'")
    image_urls = get_config().inference.dry_run.image_urls
    return [
        _dry_image_content(image_url=image_urls[image_index % len(image_urls)], img_gen_assignment=img_gen_assignment)
        for image_index in range(img_gen_assignment.nb_images)
    ]


def dry_extract_page_contents(extract_assignment: ExtractAssignment) -> list[PageContent]:
    """Dry leaf for document extraction: synthetic ``PageContent`` mocks, no provider, no storage IO.

    Sits at the ``*_and_store`` layer (eng review D10). Page views are attached above the leaf by the
    generator-level page-view logic, exactly as in a LIVE run.
    """
    log.verbose(f"🤡 DRY RUN: extract_gen_pages for '{extract_assignment.extract_handle}'")
    nb_pages: int
    if extract_assignment.extract_input.image_uri:
        nb_pages = 1
    else:
        nb_pages = get_config().inference.dry_run.nb_extract_pages
    return [
        PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="DRY RUN: OCR text"),
                images=[],
            ),
            page_view=None,
        )
        for _ in range(nb_pages)
    ]


def dry_render_page_views(render_assignment: RenderPageViewsAssignment) -> list[ImageContent]:
    """Dry leaf for page-view rendering: URL-only page-view image mocks, no pdf rendering, no storage IO.

    Fake URLs come from ``inference.dry_run.image_urls`` (validated non-empty) — the single configured
    source of truth for dry fake images, same as the img-gen mock.
    """
    log.verbose(f"🤡 DRY RUN: render_page_views for '{render_assignment.job_metadata.run_metadata.pipeline_run_id}'")
    nb_pages = get_config().inference.dry_run.nb_extract_pages
    image_urls = get_config().inference.dry_run.image_urls
    return [_dry_image_content(image_url=image_urls[page_index % len(image_urls)]) for page_index in range(nb_pages)]


def dry_search_gen_sourced_answer(search_assignment: SearchAssignment) -> SearchResultContent:
    """Dry leaf for sourced-answer search: polyfactory-built result with mock sources, no provider."""
    log.verbose(f"🤡 DRY RUN: search_gen_sourced_answer for '{search_assignment.search_handle}'")
    nb_sources = get_config().inference.dry_run.nb_list_items
    mock_sources = build_mock_objects(DocumentContent, count=nb_sources)
    return build_mock_object(SearchResultContent, sources=mock_sources)


def dry_search_gen_structured(search_object_assignment: SearchObjectAssignment) -> dict[str, Any]:
    """Dry leaf for structured search at the *boundary*: schema-built mock dumped to a dict, no provider.

    Returns a raw dict — the wire contract of the boundary arm — which the submitter re-validates
    against the original output structure class, matching the live path. The mock is built from the
    schema-reconstructed class, so an invariant the round trip drops surfaces there as
    ``DryRunObjectFidelityError``.

    ``by_alias=True`` keys the dict by the schema's property names, which is what the live arm returns
    (the provider answers the schema it was given) and what the original class accepts. Without it, a
    property the class rebuild had to rename — a python keyword, or a name shadowing a ``BaseModel``
    attribute — would come back under the renamed key and fail re-validation; see
    :func:`~pipelex.cogt.content_generation.object_revalidation.revalidate_leaf_object`.
    """
    log.verbose(f"🤡 DRY RUN: search_gen_structured for '{search_object_assignment.output_class_name}'")
    boundary_class = SchemaToModelFactory.make_from_json_schema(
        schema=search_object_assignment.output_class_schema,
        class_name=search_object_assignment.output_class_name,
    )
    return build_mock_object(boundary_class).model_dump(mode="json", by_alias=True)


def dry_search_gen_structured_object(
    search_assignment: SearchAssignment,
    *,
    output_class: type[BaseModelTypeVar],
) -> BaseModelTypeVar:
    """Dry leaf for structured search *in-process*: a mock built from the caller's own class, no provider.

    Returns the instance rather than a dump of it, and that is load-bearing rather than a convenience:
    ``build_mock_object`` runs the caller's validators, so dumping the mock for the submitter to
    re-validate would run them a second time on data they already normalized — a transforming validator
    would produce ``INV-INV-…``, the very defect the object path's ``isinstance`` short-circuit exists to
    prevent, and no short-circuit can catch it once the instance has become a dict.

    Because the mock is built from the real class, an invariant the schema round trip would have dropped
    is present at build time, so an unsatisfiable one fails earlier and louder as ``DryRunMockBuildError``
    instead of surviving into the boundary arm's ``DryRunObjectFidelityError``.

    The schema check is here because carrying the class down took away the one that used to ride along
    for free: the in-process arm built a ``SearchObjectAssignment``, whose factory called
    ``model_json_schema()`` before any run-mode branch. Polyfactory is happy to mock a class pydantic
    cannot describe, so without an explicit check ``pipelex validate`` would pass a method whose live run
    dies inside the worker on a bare ``PydanticInvalidForJsonSchema`` — and the *boundary* arm still
    builds the assignment, so a dry-run verdict would depend on how the method is deployed.
    """
    _validate_schema_is_generable(output_class=output_class)
    log.verbose(f"🤡 DRY RUN: search_gen_structured_object for '{output_class.__name__}' ({search_assignment.search_handle})")
    return build_mock_object(output_class)


def _validate_schema_is_generable(*, output_class: type[BaseModel]) -> None:
    """Prove the output class can describe itself as JSON Schema, which every structured leaf requires."""
    try:
        output_class.model_json_schema()
    except PydanticInvalidForJsonSchema as exc:
        raise OutputStructureSchemaError.for_object_class(object_class_name=output_class.__name__, reason=str(exc)) from exc
