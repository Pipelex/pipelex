import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_pipe_router
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bootstrap import ensure_pipelex_booted
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge


@pytest.mark.asyncio
class TestDirectRouterScoping:
    async def test_direct_mode_scopes_router_so_nested_dispatch_skips_hub_default(self, mocker: MockerFixture) -> None:
        """A DIRECT bridge run installs its in-process router as the active router for the whole call.

        Nested controller sub-pipes resolve their router via ``get_pipe_router()``.
        Before the fix, ``_run_direct`` never set the contextvar override, so
        nested dispatch fell back to the hub default — which is the Temporal
        router in a Temporal-enabled worker, leaking nested pipes to Temporal.
        After the fix, the run is wrapped in ``scoped_pipe_router`` so
        ``get_pipe_router()`` returns the bridge's own in-process router for the
        duration of the call, and the override is torn down on exit.
        """
        fake_pipe = mocker.MagicMock()
        fake_pipe.code = "fake_pipe"
        fake_pipe.domain_code = "fake_domain"
        fake_job = PipeJob.model_construct(
            pipe=fake_pipe,
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            job_metadata=JobMetadata(user_id="anonymous", pipeline_run_id="run-id"),
            library_crate=None,
        )
        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", return_value=fake_job)

        ensure_pipelex_booted()
        # No override is active here, so this is the hub default — exactly what a
        # nested sub-pipe would resolve if the DIRECT run failed to scope a router.
        router_before = get_pipe_router()

        captured: dict[str, object] = {}

        async def capture_active_router(_self: PipeRun, *_args: object, **_kwargs: object) -> PipeOutput:  # noqa: RUF029 — replaces an awaited method, must be a coroutine
            # Stand-in for what a nested controller does mid-run: resolve the
            # active router. It must see the scoped in-process router, NOT the
            # hub default.
            captured["router_during_run"] = get_pipe_router()
            return PipeOutput(working_memory=WorkingMemoryFactory.make_empty(), pipeline_run_id="run-id")

        mocker.patch.object(PipeRun, "run", new=capture_active_router)

        await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", orchestration_mode="direct"),
        )

        router_during_run = captured["router_during_run"]
        assert isinstance(router_during_run, PipeRouter)
        assert router_during_run is not router_before, "Nested dispatch must not resolve the hub default during a DIRECT run"
        # The scope is torn down after the run: a later resolution falls back to
        # the hub default again (override restored, not clobbered).
        assert get_pipe_router() is router_before
