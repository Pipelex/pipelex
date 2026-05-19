"""Pin the three-method registry split contract.

Phase 3 of the cross-worker tracing P0 plan replaces the single auto-creating
``_get_registry`` with two explicit methods:

- ``_get_registry_strict`` raises ``KeyError`` when the registry was never
  opened. Used by the ``_report_*_job`` paths so the runner-process case
  (no ``open_registry`` call) does not silently accumulate orphan registries.
- ``_get_or_create_registry`` creates on miss. Used by ``inject_tokens_usages``
  (the P1 cross-worker assembly path) and ``generate_report`` for runs not
  opened on this process.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.reporting.reporting_manager import ReportingManager


def _make_llm_job(pipeline_run_id: str) -> LLMJob:
    now = datetime.now(timezone.utc)
    job_metadata = JobMetadata(
        user_id="test_user",
        pipeline_run_id=pipeline_run_id,
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        unit_job_id=UnitJobId.LLM_GEN_TEXT,
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )


class TestNoOrphanRegistries:
    """Phase 3 contract: runner-process reporting must not silently auto-create registries."""

    def test_runner_does_not_accumulate_registries(self) -> None:
        """When open_registry was never called, _report_llm_job must not insert a registry.

        The runner process gets activities reported with pipeline_run_ids it has never seen.
        Pre-Phase-3 behavior auto-created an empty registry on every miss, accumulating
        memory for every distinct pipeline_run_id. Phase 3 makes _report_*_job silently skip
        the add (the usage event still emits via the runner fallback path).
        """
        manager = ReportingManager()
        manager.setup()

        manager.report_inference_job(_make_llm_job("never_opened"))

        assert "never_opened" not in manager._usage_registries  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_direct_mode_still_accumulates_registry(self) -> None:
        """When open_registry was called for this run, _report_llm_job must add to it."""
        manager = ReportingManager()
        manager.setup()
        manager.open_registry("run_x")

        manager.report_inference_job(_make_llm_job("run_x"))

        registry = manager._get_or_create_registry("run_x")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        usages = registry.get_current_tokens_usage()
        assert len(usages) == 1
        assert usages[0].nb_tokens_by_category[TokenCategory.INPUT] == 100

    def test_inject_tokens_usages_still_creates_on_miss(self) -> None:
        """inject_tokens_usages preserves auto-create behavior via _get_or_create_registry.

        This is the P1 cross-worker assembly path: usage records collected from trace
        events get injected into a registry that may not have been opened on this
        process — the registry must be created on demand.
        """
        manager = ReportingManager()
        manager.setup()

        tokens_usage = LLMTokensUsage(
            job_metadata=_make_llm_job("new_run").job_metadata,
            inference_model_name="test-model",
            inference_model_id="test-model-id",
            unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
            nb_tokens_by_category={TokenCategory.INPUT: 50, TokenCategory.OUTPUT: 25},
        )
        manager.inject_tokens_usages(pipeline_run_id="new_run", tokens_usages=[tokens_usage])

        registry = manager._get_or_create_registry("new_run")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert len(registry.get_current_tokens_usage()) == 1

    def test_get_registry_strict_raises_when_missing(self) -> None:
        """_get_registry_strict raises KeyError on miss — distinct from _get_or_create_registry."""
        manager = ReportingManager()
        manager.setup()

        with pytest.raises(KeyError):
            manager._get_registry_strict("never_opened")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_generate_report_for_unopened_run_creates_empty_registry_and_renders(self) -> None:
        """generate_report on a never-opened run does not crash; renders empty cost report."""
        manager = ReportingManager()
        manager.setup()

        # Must not raise.
        manager.generate_report(pipeline_run_id="never_opened")
