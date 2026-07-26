"""Characterization test for :func:`pipeline_run_setup` (D4).

Pins the *current* observable behavior of ``pipeline_run_setup`` before the
Phase-1 extraction of the ``acquire_library`` / ``prepare_pipe_job`` seams, so
that "no behavior change" is verified, not merely claimed, on this long,
ordering-sensitive setup function.

What is pinned here:

- **Success path (DRY + mock inputs):** the returned ``PipeJob`` resolves the
  requested pipe with ``run_mode = DRY`` and mock working memory for the pipe's
  needed inputs; the library is left **open and current** (``pipeline_run_setup``
  does *not* tear down on success — the caller, ``execute``, owns
  teardown); exactly one ``PIPELINE_EXECUTE`` telemetry event is emitted; and the
  pipeline is registered in the pipeline manager.
- **``search_domain_codes`` in-place mutation (trap at the domain-insert block):**
  a non-empty caller list is mutated in place — the pipe's domain is inserted at
  the front. Pinned so the extraction preserves it consciously (a "pure" builder
  would be tempted to copy the list, which would be a behavior change).
- **Empty inputs behave like no inputs:** an empty ``PipelineInputs`` with
  ``mock_inputs=False`` yields an empty working memory, identical to
  ``inputs=None``. This characterizes the end-to-end behavior but does *not*
  discriminate ``if inputs:`` from ``inputs is not None`` (root is ``{}`` under
  either); that invariant is pinned at the normalize gate by
  ``test_prepare_pipe_job_skips_normalize_for_empty_inputs`` in
  ``test_execution_seams.py``.
- **Load-failure path (tears down — no leak):** a failure while resolving the
  pipe (here a ``pipe_code`` absent from the bundle, failing at
  ``get_required_pipe``) tears the opened library down and restores the outer
  current-library before propagating. This is an **intentional fix**
  introduced by the seam extraction: previously the open/load/resolve ran
  *outside* ``pipeline_run_setup``'s ``try`` so this exact failure leaked the
  library (``execute``'s ``finally`` only tore down when setup returned
  a ``library_id``, which it never did). ``acquire_library`` now owns load-time
  teardown and the recomposed ``try``/``finally`` owns the post-acquire window,
  matching the already-hardened ``validate_bundle``.
- **Success path leaves no per-run reporting state (Phase 4 — leak fixed by removal):** a
  successful run through ``execute`` leaves the ``ReportingManager`` with no accumulated
  per-run state — the per-run event-log context is cleared on the way out, and the live usage
  registry has been removed entirely, so the success-path leak it used to suffer (a per-run
  registry opened in setup and never closed) is structurally impossible.
- **Failure after acquire restores the outer current-library:** when the caller
  had an outer current-library set, a post-acquire failure restores it rather
  than clobbering it to ``None`` — mirroring ``acquire_library``'s own load-failure
  teardown and the four ``validate_bundle`` entry points.
"""

from collections.abc import Callable

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.method_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_pipeline_manager, set_current_library
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.service_hub import get_report_delegate, get_telemetry_manager
from pipelex.system.configuration.configs import NdjsonTracingConfig, PipelineExecutionConfig, TracingBackend
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
    return get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


def _no_mock_config() -> PipelineExecutionConfig:
    return get_config().pipelex.pipeline_execution_config.with_execution_overrides(
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
            clear_current_library()

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
            clear_current_library()

    async def test_empty_inputs_behave_like_no_inputs(self) -> None:
        pipe_job, _, library_id = await pipeline_run_setup(
            execution_config=_no_mock_config(),
            mthds_contents=[_CHAR_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
            inputs=PipelineInputs(),
        )
        try:
            # Empty PipelineInputs yields empty working memory and does not crash, end-to-end through
            # pipeline_run_setup. NOTE: this does NOT discriminate `if inputs:` from `inputs is not None`
            # — an empty PipelineInputs maps to root == {} under either semantic, so the assertion holds
            # either way. The falsy-`inputs` invariant is pinned at the normalize gate by
            # test_prepare_pipe_job_skips_normalize_for_empty_inputs in test_execution_seams.py.
            assert pipe_job.get_working_memory().root == {}
        finally:
            get_library_manager().teardown(library_id=library_id)
            clear_current_library()

    async def test_load_failure_tears_down_library(self, mocker: MockerFixture) -> None:
        # A failure while resolving the pipe (pipe_code absent from the bundle ->
        # PipeNotFoundError at get_required_pipe) tears the opened library down and
        # restores the outer current-library before propagating — no leak.
        #
        # NOTE (intentional behavior change in the Phase-1 seam extraction): before
        # acquire_library / prepare_pipe_job, the open+load+resolve ran *outside*
        # pipeline_run_setup's `try`, so this exact failure leaked the library
        # (teardown was never called). acquire_library now owns load-time teardown and
        # the recomposed try/finally owns the post-acquire window — matching the
        # already-hardened validate_bundle. This is a deliberate fix, not a regression.
        #
        # The current-library assertion captures the prev baseline rather than hardcoding
        # ``is None``: the failure path now *restores* the outer current-library (when none
        # was set, as here, that resolves to None). Asserting restoration-to-prev keeps the
        # test correct under xdist's per-worker shared current-library state. See the
        # dedicated outer-restore case below for the non-None branch.
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        teardown_before = teardown_spy.call_count
        prev_library_id = get_current_library_id_or_none()

        with pytest.raises(PipeNotFoundError):
            await pipeline_run_setup(
                execution_config=_dry_mock_config(),
                mthds_contents=[_CHAR_MTHDS],
                pipe_code="absent_pipe",
                pipe_run_mode=PipeRunMode.DRY,
            )

        assert teardown_spy.call_count == teardown_before + 1
        assert get_current_library_id_or_none() == prev_library_id

    async def test_success_path_leaves_no_per_run_reporting_state(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        # Phase 4: the live usage registry is removed entirely, so the success-path leak (a per-run
        # registry opened in pipeline_run_setup and never closed) is structurally impossible. Run a real
        # DRY pipeline through execute with tracing + costs on (so a usage event-log context IS
        # registered during the run), then assert the ReportingManager carries NO per-run state afterward:
        # the registry concept no longer exists, and the event-log context was cleared on the success path.
        traces_dir = str(tmp_path_factory.mktemp("char_no_leak"))
        tracing_config = get_config().pipelex.tracing_config
        mocker.patch.object(tracing_config, "is_enabled", True)
        mocker.patch.object(tracing_config, "backend", TracingBackend.NDJSON)
        mocker.patch.object(tracing_config, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

        delegate = get_report_delegate()
        # The registry attribute is gone for good — the leak cannot recur.
        assert not hasattr(delegate, "_usage_registries")

        execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=False,
            generate_usage=True,
            mock_inputs=True,
        )
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)
        response = await runner.execute(pipe_code="echo_topic", mthds_contents=[_CHAR_MTHDS])

        assert not hasattr(delegate, "_usage_registries")
        # This run registered a usage event-log context (tracing + costs on); the success path must have
        # cleared it. Assert against THIS run's key rather than global emptiness — _event_log_contexts is a
        # process-global singleton that sibling tests on the same xdist worker can populate.
        if isinstance(delegate, ReportingManager):
            assert response.pipeline_run_id not in delegate._event_log_contexts  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    async def test_failure_after_acquire_restores_outer_current_library(self, load_empty_library: Callable[[], str]) -> None:
        # acquire_library restores the outer current-library on its own load failure; the wrapper's
        # post-acquire failure path must do the same (mirror validate_bundle), or a post-acquire failure
        # clobbers an outer caller's current-library to None — the latent bug the Phase-2 BundleValidator
        # looping reuse would hit. Set an outer current-library, trigger a post-acquire failure
        # (absent_pipe fails at get_required_pipe, after acquire_library), and assert it is restored.
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            with pytest.raises(PipeNotFoundError):
                await pipeline_run_setup(
                    execution_config=_dry_mock_config(),
                    mthds_contents=[_CHAR_MTHDS],
                    pipe_code="absent_pipe",
                    pipe_run_mode=PipeRunMode.DRY,
                )
            # Restored to the outer id, not clobbered to None.
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()

    async def test_failure_when_outer_is_run_library_clears_instead_of_dangling(self) -> None:
        # Edge of the outer-restore path: when the caller passes a library_id that is ALSO the outer
        # current-library, prev_library_id == library_id. Naively restoring then tearing down the same
        # id leaves the current-library ContextVar pointing at a TORN-DOWN library. The guard
        # (prev != library_id) routes this through clear_current_library so no dangling pointer survives.
        # acquire_library re-opens the same id idempotently, and the failing run tears that library down.
        # Unlike test_failure_after_acquire_restores_outer_current_library (which uses a fresh auto run id,
        # so prev != run id), here the run id collides with the outer one — the case validate_bundle never
        # hits because it always opens a fresh uuid.
        library_manager = get_library_manager()
        collide_library_id, _ = library_manager.open_library()
        set_current_library(library_id=collide_library_id)
        try:
            with pytest.raises(PipeNotFoundError):
                await pipeline_run_setup(
                    execution_config=_dry_mock_config(),
                    library_id=collide_library_id,
                    mthds_contents=[_CHAR_MTHDS],
                    pipe_code="absent_pipe",
                    pipe_run_mode=PipeRunMode.DRY,
                )
            # Cleared, not left dangling at the just-torn-down collide id.
            assert get_current_library_id_or_none() is None
        finally:
            clear_current_library()
