"""Characterization test for :func:`pipeline_run_setup` (D4).

Pins the *current* observable behavior of ``pipeline_run_setup`` before the
Phase-1 extraction of the ``acquire_library`` / ``prepare_pipe_job`` seams, so
that "no behavior change" is verified, not merely claimed, on this long,
ordering-sensitive setup function.

What is pinned here:

- **Success path (DRY + mock inputs):** the returned ``PipeJob`` resolves the
  requested pipe with ``run_mode = DRY`` and mock working memory for the pipe's
  needed inputs; the library is left **open and current** (``pipeline_run_setup``
  does *not* tear down on success — the caller, ``execute_pipeline``, owns
  teardown); exactly one ``PIPELINE_EXECUTE`` telemetry event is emitted; and the
  pipeline is registered in the pipeline manager.
- **``search_domain_codes`` in-place mutation (trap at the domain-insert block):**
  a non-empty caller list is mutated in place — the pipe's domain is inserted at
  the front. Pinned so the extraction preserves it consciously (a "pure" builder
  would be tempted to copy the list, which would be a behavior change).
- **Empty inputs behave like no inputs (truthiness trap):** an empty
  ``PipelineInputs`` with ``mock_inputs=False`` yields an empty working memory,
  identical to ``inputs=None`` — i.e. the ``if inputs:`` truthiness check, not
  ``inputs is not None``.
- **Load-failure path (tears down — no leak):** a failure while resolving the
  pipe (here a ``pipe_code`` absent from the bundle, failing at
  ``get_required_pipe``) tears the opened library down and clears the
  current-library ContextVar before propagating. This is an **intentional fix**
  introduced by the seam extraction: previously the open/load/resolve ran
  *outside* ``pipeline_run_setup``'s ``try`` so this exact failure leaked the
  library (``execute_pipeline``'s ``finally`` only tore down when setup returned
  a ``library_id``, which it never did). ``acquire_library`` now owns load-time
  teardown and the recomposed ``try``/``finally`` owns the post-acquire window,
  matching the already-hardened ``validate_bundle``.
"""

import pytest
from mthds.models.pipeline_inputs import PipelineInputs
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.hub import (
    get_current_library_id_or_none,
    get_library_manager,
    get_pipeline_manager,
    get_telemetry_manager,
    teardown_current_library,
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.telemetry.events import EventName

_CHAR_DOMAIN = "prs_char"
_CHAR_MTHDS = f"""
domain = "{_CHAR_DOMAIN}"
description = "Minimal bundle for pipeline_run_setup characterization"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to set up a PipeJob"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _dry_mock_config() -> PipelineExecutionConfig:
    return get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


def _no_mock_config() -> PipelineExecutionConfig:
    return get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=False,
        mock_inputs=False,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunSetupCharacterization:
    async def test_success_path_builds_dry_job_and_leaves_library_open(self, mocker: MockerFixture) -> None:
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        track_event_spy = mocker.spy(get_telemetry_manager(), "track_event")
        teardown_before = teardown_spy.call_count

        pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
            execution_config=_dry_mock_config(),
            mthds_contents=[_CHAR_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
        )
        try:
            # Job correctness: bare pipe code, DRY run mode, mock working memory for the needed input.
            assert pipe_job.pipe.code == "echo_topic"
            assert pipe_job.pipe.domain_code == _CHAR_DOMAIN
            assert pipe_job.pipe_run_params.run_mode.is_dry
            working_memory = pipe_job.get_working_memory()
            assert "subject" in working_memory.root

            # Library left open + current on success (caller owns teardown).
            opened_library_id, _ = open_spy.spy_return
            assert library_id == opened_library_id
            assert teardown_spy.call_count == teardown_before
            assert get_current_library_id_or_none() == library_id

            # Exactly one PIPELINE_EXECUTE telemetry event.
            execute_events = [call for call in track_event_spy.call_args_list if call.kwargs.get("event_name") == EventName.PIPELINE_EXECUTE]
            assert len(execute_events) == 1

            # Pipeline registered.
            assert get_pipeline_manager().get_optional_pipeline(pipeline_run_id) is not None
        finally:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()

    async def test_search_domain_codes_list_is_mutated_in_place(self) -> None:
        caller_domains = ["zzz_other_domain"]
        _, _, library_id = await pipeline_run_setup(
            execution_config=_dry_mock_config(),
            mthds_contents=[_CHAR_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
            search_domain_codes=caller_domains,
        )
        try:
            # The pipe's domain is inserted at the front of the caller's (non-empty) list, in place.
            assert caller_domains == [_CHAR_DOMAIN, "zzz_other_domain"]
        finally:
            get_library_manager().teardown(library_id=library_id)
            teardown_current_library()

    async def test_empty_inputs_behave_like_no_inputs(self) -> None:
        pipe_job, _, library_id = await pipeline_run_setup(
            execution_config=_no_mock_config(),
            mthds_contents=[_CHAR_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
            inputs=PipelineInputs(),
        )
        try:
            # Empty PipelineInputs is falsy: no inputs are materialized, so the working memory
            # is empty (same as inputs=None). Pins `if inputs:` rather than `inputs is not None`.
            assert pipe_job.get_working_memory().root == {}
        finally:
            get_library_manager().teardown(library_id=library_id)
            teardown_current_library()

    async def test_load_failure_tears_down_library(self, mocker: MockerFixture) -> None:
        # A failure while resolving the pipe (pipe_code absent from the bundle ->
        # PipeNotFoundError at get_required_pipe) tears the opened library down and
        # clears the current-library ContextVar before propagating — no leak.
        #
        # NOTE (intentional behavior change in the Phase-1 seam extraction): before
        # acquire_library / prepare_pipe_job, the open+load+resolve ran *outside*
        # pipeline_run_setup's `try`, so this exact failure leaked the library
        # (teardown was never called). acquire_library now owns load-time teardown and
        # the recomposed try/finally owns the post-acquire window — matching the
        # already-hardened validate_bundle. This is a deliberate fix, not a regression.
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        teardown_before = teardown_spy.call_count

        with pytest.raises(PipeNotFoundError):
            await pipeline_run_setup(
                execution_config=_dry_mock_config(),
                mthds_contents=[_CHAR_MTHDS],
                pipe_code="absent_pipe",
                pipe_run_mode=PipeRunMode.DRY,
            )

        assert teardown_spy.call_count == teardown_before + 1
        assert get_current_library_id_or_none() is None
