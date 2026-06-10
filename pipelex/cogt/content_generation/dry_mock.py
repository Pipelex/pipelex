"""Leaf-level inference mocking shared by ``--dry-run`` and ``--mock-inference``.

Two triggers, one mechanism. Both fake the AI call *at the cogt leaf* — the
lowest point where ``ContentGenerator`` (direct, inline) and the Temporal
activities (``act_llm_gen_*`` and friends) converge — so a single branch covers
both backends and ``run_mode`` stays orthogonal to backend choice (D-plan §3.5):

- ``--dry-run`` (``CogtRunParams.run_mode == DRY``, carried on every assignment):
  the leaf routes to the :func:`dry_llm_gen_text` / :func:`dry_llm_gen_object` /
  ... helpers here, which report a **zero-token** synthetic LLM job via
  :func:`report_dry_llm_job`. Zero tokens ⇒ ``AggregatedCosts.has_reportable_usage``
  is False ⇒ the end-of-run cost report is suppressed (correct: a dry run did no
  real work). Non-LLM dry leaves (img-gen / extract / render / search /
  templating) mint synthetic outputs without reporting usage. For img-gen and
  extract, the DRY branch lives at the ``*_and_store`` layer — one step above the
  raw provider leaf — so a dry run performs **no storage IO** (eng review D10).
- ``--mock-inference`` (``run_mode=LIVE`` + ``JobMetadata.is_mock_inference``):
  the LLM leaf routes to :func:`mock_llm_gen_text` / :func:`mock_llm_gen_object` /
  :func:`mock_llm_gen_object_list`, which report **non-zero** synthetic usage via
  :func:`report_mock_inference_llm_job`. Non-zero tokens ⇒ a cost report *renders*.
  This is the durable reason the two modes differ at the reporting layer: only a
  non-zero mock can validate cross-worker cost-report rendering cheaply and
  deterministically (no provider spend). Non-LLM leaves have no reportable mock
  and keep their ``MockInferenceUnsupportedError`` fail-loud guard.

This module is the single home for "what a mocked inference produces". Object
mocks are built from the **schema-reconstructed** class on both backends (one
code path, identical mock everywhere); exotic format constraints must declare
``examples`` / ``mock_format`` — see ``MockInferenceObjectFidelityError``.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError

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
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.content_generation.exceptions import DryRunMockBuildError
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.cogt.image.image_size import ImageSize
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
from pipelex.hub import get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

# Sentinel model identifiers so a synthetic usage record is never confused with real inference.
DRY_RUN_INFERENCE_MODEL_NAME = "dry_run"
DRY_RUN_INFERENCE_MODEL_ID = "dry_run"
MOCK_INFERENCE_MODEL_NAME = "mock_inference"
MOCK_INFERENCE_MODEL_ID = "mock_inference"

# Synthetic, deterministic, clearly non-real token counts for ``--mock-inference``. Non-zero so the
# assembled usage is reportable (``AggregatedCosts.has_reportable_usage`` True → the cost report renders),
# which is exactly what ``--dry-run``'s zero-token usage deliberately suppresses. Input/output differ so
# the rendered table distinguishes the two columns. Cost stays 0 (``unit_costs={}``): a mocked run has
# token usage but no real spend — the "free model" reporting case.
MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY: NbTokensByCategoryDict = {
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
    :func:`report_mock_inference_llm_job` (non-zero tokens). Reporting it makes the runner-side
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


def report_dry_llm_job(job_metadata: JobMetadata, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None:
    """Report a zero-token synthetic LLM job for a ``--dry-run`` inference (cost report suppressed)."""
    _report_synthetic_llm_job(
        job_metadata=job_metadata,
        llm_setting=llm_setting,
        llm_prompt=llm_prompt,
        inference_model_name=DRY_RUN_INFERENCE_MODEL_NAME,
        inference_model_id=DRY_RUN_INFERENCE_MODEL_ID,
        nb_tokens_by_category={},
    )


def report_mock_inference_llm_job(job_metadata: JobMetadata, llm_setting: LLMSetting, llm_prompt: LLMPrompt) -> None:
    """Report a non-zero synthetic LLM job for a ``--mock-inference`` call (cost report renders)."""
    _report_synthetic_llm_job(
        job_metadata=job_metadata,
        llm_setting=llm_setting,
        llm_prompt=llm_prompt,
        inference_model_name=MOCK_INFERENCE_MODEL_NAME,
        inference_model_id=MOCK_INFERENCE_MODEL_ID,
        nb_tokens_by_category=dict(MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY),
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


def build_mock_objects(model_class: type[BaseModelTypeVar], count: int) -> list[BaseModelTypeVar]:
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


def _mock_text(*, llm_prompt: LLMPrompt, llm_setting: LLMSetting) -> str:
    truncate_length = get_config().pipelex.dry_run_config.text_gen_truncate_length
    prompt_truncated = llm_prompt.desc(truncate_text_length=truncate_length)
    return f"MOCK INFERENCE • llm_setting={llm_setting.desc()} • prompt={prompt_truncated}"


def mock_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    """Leaf mock for ``llm_gen_text``: synthetic text + reportable usage, no provider call."""
    job_metadata = llm_assignment.job_metadata
    log.verbose(f"🤡 MOCK INFERENCE: llm_gen_text for '{job_metadata.pipeline_run_id}'")
    report_mock_inference_llm_job(
        job_metadata=job_metadata,
        llm_setting=llm_assignment.llm_setting,
        llm_prompt=llm_assignment.llm_prompt,
    )
    return _mock_text(llm_prompt=llm_assignment.llm_prompt, llm_setting=llm_assignment.llm_setting)


def _reconstruct_object_class(object_assignment: ObjectAssignment) -> type[BaseModel]:
    """Reconstruct the object's model class from its JSON schema.

    Shared by the dry and mock-inference object mocks. The leaf carries only the JSON
    schema (not the original class), so the class is rebuilt via :class:`SchemaToModelFactory`.
    This is the single schema-based mock site: both backends build the same mock, and fidelity
    bugs surface in cheap local unit tests instead of only on a worker (pre-flight decision 2).
    """
    return SchemaToModelFactory.make_from_json_schema(
        schema=object_assignment.object_class_schema,
        class_name=object_assignment.object_class_name,
    )


def _nb_list_items(object_assignment: ObjectAssignment) -> int:
    """Resolve the object-list mock length: the assignment's fixed ``nb_items`` wins (D11)."""
    return object_assignment.nb_items or get_config().pipelex.dry_run_config.nb_list_items


_ReportLLMJobFunc = Callable[[JobMetadata, LLMSetting, LLMPrompt], None]


def _leaf_gen_object(object_assignment: ObjectAssignment, report_func: _ReportLLMJobFunc) -> BaseModel:
    """Shared object-mock pipeline: reconstruct the class from its schema, report once, build one mock.

    Built from the schema-reconstructed class (the leaf carries only the JSON schema, not the original
    class), so format hints encoded via ``json_schema_extra`` that datamodel-code-generator drops on
    round-trip are not honored — exotic-format schemas may yield mock data the original class would
    reject. The generator re-validates against the original class and re-raises that failure as
    ``MockInferenceObjectFidelityError`` (review F2); declare ``examples`` / ``mock_format`` on the
    constrained fields to fix it.

    Reports exactly once — the live leaf makes one ``gen_object`` call (a list is one call against a
    list-wrapper schema), so a single ``UsageReportEvent`` matches the real one-call topology that
    cross-worker assertions count.
    """
    item_class = _reconstruct_object_class(object_assignment)
    llm_assignment = object_assignment.llm_assignment_for_object
    report_func(llm_assignment.job_metadata, llm_assignment.llm_setting, llm_assignment.llm_prompt)
    return build_mock_object(item_class)


def _leaf_gen_object_list(object_assignment: ObjectAssignment, report_func: _ReportLLMJobFunc) -> list[BaseModel]:
    """List counterpart of :func:`_leaf_gen_object`: one report, ``nb_items`` builds (D11)."""
    item_class = _reconstruct_object_class(object_assignment)
    llm_assignment = object_assignment.llm_assignment_for_object
    report_func(llm_assignment.job_metadata, llm_assignment.llm_setting, llm_assignment.llm_prompt)
    return build_mock_objects(item_class, _nb_list_items(object_assignment))


def mock_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    """Leaf mock for ``llm_gen_object``: schema-built mock + reportable (non-zero) usage."""
    return _leaf_gen_object(object_assignment, report_func=report_mock_inference_llm_job)


def mock_llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]:
    """Leaf mock for ``llm_gen_object_list``: ``nb_items`` builds + one reportable usage event.

    The ``pipe_code='mock_main'`` first-item coordination that satisfies ``BundleHeaderSpec.main_pipe``
    during bundle dry-validation lives ONLY in ``ContentGeneratorDry.make_object_list`` today; the leaf
    mocks (this one and the dry one) do not perform it. ``--mock-inference`` never drives bundle
    dry-validation so it never needs it; the dry leaf gains it in Phase B2 via the shared
    ``stamp_mock_main_coordination()`` helper when ``ContentGeneratorDry`` is deleted (see
    ``wip/dry-run-refactor/followup-leaf-run-mode-mock.md``).
    """
    return _leaf_gen_object_list(object_assignment, report_func=report_mock_inference_llm_job)


# --- Dry leaf helpers (``run_mode == DRY``) -------------------------------------------------------
#
# Each helper is the leaf-level counterpart of the corresponding ``ContentGeneratorDry`` method:
# same synthetic output, but minted at the leaf so it runs identically inline (direct backend) and
# inside a Temporal activity (the backend dispatches normally; the leaf mocks).


def _dry_text_gen_truncate_length() -> int:
    return get_config().pipelex.dry_run_config.text_gen_truncate_length


def dry_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    """Dry leaf for ``llm_gen_text``: zero-token synthetic job report + a ``DRY RUN:`` marker string."""
    job_metadata = llm_assignment.job_metadata
    log.verbose(f"🤡 DRY RUN: llm_gen_text for '{job_metadata.pipeline_run_id}'")
    report_dry_llm_job(
        job_metadata=job_metadata,
        llm_setting=llm_assignment.llm_setting,
        llm_prompt=llm_assignment.llm_prompt,
    )
    prompt_truncated = llm_assignment.llm_prompt.desc(truncate_text_length=_dry_text_gen_truncate_length())
    return f"DRY RUN: llm_gen_text • llm_setting={llm_assignment.llm_setting.desc()} • prompt={prompt_truncated}"


def dry_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    """Dry leaf for ``llm_gen_object``: schema-built mock instance + zero-token job report."""
    log.verbose(f"🤡 DRY RUN: llm_gen_object for '{object_assignment.object_class_name}'")
    return _leaf_gen_object(object_assignment, report_func=report_dry_llm_job)


def dry_llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]:
    """Dry leaf for ``llm_gen_object_list``: ``nb_items`` schema-built mocks + one zero-token report."""
    log.verbose(f"🤡 DRY RUN: llm_gen_object_list for '{object_assignment.object_class_name}'")
    return _leaf_gen_object_list(object_assignment, report_func=report_dry_llm_job)


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
    return (
        f"DRY RUN: templating_gen_text • context={templating_assignment.context} • "
        f"jinja2={jinja2_truncated} • templating_style={templating_assignment.templating_style} • "
        f"template_category={templating_assignment.category}"
    )


def _dry_image_content(image_url: str, img_gen_assignment: ImgGenAssignment | None = None) -> ImageContent:
    image_content = ImageContent(
        url=image_url,
        public_url=image_url,
        mime_type="image/jpeg",
        size=ImageSize(width=1024, height=1024),
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
    image_urls = get_config().pipelex.dry_run_config.image_urls
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
        nb_pages = get_config().pipelex.dry_run_config.nb_extract_pages
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

    Fake URLs come from ``dry_run_config.image_urls`` (validated non-empty) — the single configured
    source of truth for dry fake images, same as the img-gen mock.
    """
    log.verbose(f"🤡 DRY RUN: render_page_views for '{render_assignment.job_metadata.pipeline_run_id}'")
    nb_pages = get_config().pipelex.dry_run_config.nb_extract_pages
    image_urls = get_config().pipelex.dry_run_config.image_urls
    return [_dry_image_content(image_url=image_urls[page_index % len(image_urls)]) for page_index in range(nb_pages)]


def dry_search_gen_sourced_answer(search_assignment: SearchAssignment) -> SearchResultContent:
    """Dry leaf for sourced-answer search: polyfactory-built result with mock sources, no provider."""
    log.verbose(f"🤡 DRY RUN: search_gen_sourced_answer for '{search_assignment.search_handle}'")
    nb_sources = get_config().pipelex.dry_run_config.nb_list_items
    mock_sources = build_mock_objects(DocumentContent, nb_sources)
    return build_mock_object(SearchResultContent, sources=mock_sources)


def dry_search_gen_structured(search_object_assignment: SearchObjectAssignment) -> dict[str, Any]:
    """Dry leaf for structured search: schema-built mock dumped to a dict, no provider.

    Returns a raw dict (the leaf contract) which the submitter re-validates against the original
    output structure class, matching the live path.
    """
    log.verbose(f"🤡 DRY RUN: search_gen_structured for '{search_object_assignment.output_class_name}'")
    output_class = SchemaToModelFactory.make_from_json_schema(
        schema=search_object_assignment.output_class_schema,
        class_name=search_object_assignment.output_class_name,
    )
    return build_mock_object(output_class).model_dump(mode="json")
