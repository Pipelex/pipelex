"""Leaf-level inference mocking shared by ``--dry-run`` and ``--mock-inference``.

Two triggers, one mechanism. Both fake the AI call *at the cogt leaf* — the
lowest point where ``ContentGenerator`` (direct) and the Temporal activities
(``act_llm_gen_*``) converge — so a single branch covers both execution modes:

- ``--dry-run`` (``run_mode=DRY``): ``ContentGeneratorDry`` is swapped in
  pre-dispatch by each operator; it reports a **zero-token** synthetic LLM job
  via :func:`report_dry_llm_job`. Zero tokens ⇒ ``AggregatedCosts.has_reportable_usage``
  is False ⇒ the end-of-run cost report is suppressed (correct: a dry run did no
  real work).
- ``--mock-inference`` (``run_mode=LIVE`` + ``JobMetadata.is_mock_inference``):
  operators dispatch normally and the leaf itself routes to the
  :func:`mock_llm_gen_text` / :func:`mock_llm_gen_object` /
  :func:`mock_llm_gen_object_list` helpers here, which report **non-zero**
  synthetic usage via :func:`report_mock_inference_llm_job`. Non-zero tokens ⇒ a
  cost report *renders*. This is the durable reason the two modes differ at the
  reporting layer: only a non-zero mock can validate cross-worker cost-report
  rendering cheaply and deterministically (no provider spend).

This module is the single home for "what a mocked inference produces". The
follow-up that makes ``run_mode=DRY`` honor the backend
(``wip/dry-run-refactor/followup-leaf-run-mode-mock.md``) re-keys the leaf branch
from ``is_mock_inference`` to ``run_mode`` and folds ``ContentGeneratorDry`` into
these helpers — so the helpers, not the call sites, are the load-bearing piece.
"""

from datetime import datetime

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.hub import get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
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


def build_mock_object(model_class: type[BaseModelTypeVar]) -> BaseModelTypeVar:
    """Build one mock instance of ``model_class`` via the dry-run polyfactory.

    Runs validators so the mock is valid; fields with format constraints
    (snake_case, PascalCase, ...) should declare ``examples`` / ``mock_format`` so
    polyfactory uses those instead of random strings.
    """
    return DryRunFactory.make_dry_run_factory(model_class).build()


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


def mock_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    """Leaf mock for ``llm_gen_object``: a polyfactory-built instance of the schema model + reportable usage.

    Built from the schema-reconstructed class (the leaf carries only the JSON schema, not the original
    class), so format hints encoded via ``json_schema_extra`` that datamodel-code-generator drops on
    round-trip are not honored — exotic-format schemas may yield mock data the original class would
    reject. This is the known object-mock fidelity gap (followup-leaf-run-mode-mock.md §8); the direct
    ``ContentGeneratorDry`` dry-run path keeps full fidelity by building the original class.
    """
    llm_assignment = object_assignment.llm_assignment_for_object
    content_class = SchemaToModelFactory.make_from_json_schema(
        schema=object_assignment.object_class_schema,
        class_name=object_assignment.object_class_name,
    )
    report_mock_inference_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_setting=llm_assignment.llm_setting,
        llm_prompt=llm_assignment.llm_prompt,
    )
    return build_mock_object(content_class)


def mock_llm_gen_object_list(object_assignment: ObjectAssignment) -> list[BaseModel]:
    """Leaf mock for ``llm_gen_object_list``: ``nb_list_items`` builds + one reportable usage event.

    Reports once — the live leaf makes one ``gen_object`` call against a list-wrapper schema, so a
    single ``UsageReportEvent`` matches the real one-call topology (cross-worker assertions count
    one usage record per LLM call).
    """
    llm_assignment = object_assignment.llm_assignment_for_object
    item_class = SchemaToModelFactory.make_from_json_schema(
        schema=object_assignment.object_class_schema,
        class_name=object_assignment.object_class_name,
    )
    nb_list_items = get_config().pipelex.dry_run_config.nb_list_items
    items: list[BaseModel] = [build_mock_object(item_class) for _ in range(nb_list_items)]
    report_mock_inference_llm_job(
        job_metadata=llm_assignment.job_metadata,
        llm_setting=llm_assignment.llm_setting,
        llm_prompt=llm_assignment.llm_prompt,
    )
    return items
