"""Integration tests for BundleValidator's real composition (Phase 2).

Unlike the unit suite (which mocks the seams + the run primitive), these run a real pipe DRY
through the composed stack — ``prepare_pipe_job`` + a direct in-process ``PipeRun`` + real
telemetry — to pin the contracts mocks cannot: that a real DRY run classifies SUCCESS, that each
sweep dry-runs its pipes under a UNIQUE per-sweep pipeline run id (and that concurrent sweeps
genuinely overlap and both succeed — the live registry that once made a constant id collide is
gone, so this is now a plain concurrency guarantee), and that the sweep emits exactly one
``PIPE_DRY_RUN`` event with no stray runner ``PIPELINE_EXECUTE`` / ``PIPELINE_COMPLETE`` events.
"""

import asyncio
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.hub import (
    clear_current_library,
    get_library_manager,
    get_required_pipe,
    get_telemetry_manager,
)
from pipelex.pipeline import bundle_validator
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.system.telemetry.events import EventName

_BV_DOMAIN = "bundle_validator_test"
_BV_MTHDS = f"""
domain = "{_BV_DOMAIN}"
description = "Minimal bundle for BundleValidator integration tests"
main_pipe = "echo_topic"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to dry-run through BundleValidator"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""

# A bundle whose PipeParallel controller references an UNLOADED cross-package sub-pipe
# ("ext->otherpkg.missing_pipe"). PipeParallel resolves its branches with an unguarded
# get_required_pipe, so validate_with_libraries raises PipeNotFoundError — the sweep must record the
# controller SKIPPED and still classify the sibling implemented leaf, never abort (finding #1 / D7).
_BV_XPKG_DOMAIN = "bundle_validator_xpkg"
_BV_XPKG_MTHDS = f"""
domain = "{_BV_XPKG_DOMAIN}"
description = "Bundle exercising cross-package SKIPPED tolerance in the step-1 wiring pass"

[concept.Doc]
description = "A document"

[pipe.implemented_leaf]
type = "PipeLLM"
description = "A fully implemented sibling leaf"
inputs = {{ doc = "Doc" }}
output = "Text"
prompt = "Summarize $doc"

[pipe.cross_parallel]
type = "PipeParallel"
description = "Parallel referencing an unloaded cross-package branch"
inputs = {{ doc = "Doc" }}
output = "Text"
add_each_output = true
combined_output = "Text"
branches = [
  {{ pipe = "ext->otherpkg.missing_pipe", result = "branch_result" }},
]
"""


@pytest.mark.asyncio(loop_scope="class")
class TestBundleValidatorIntegration:
    async def test_validate_pipes_success_real_path(self) -> None:
        library_manager = get_library_manager()
        library_id = "bv_success_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            results = await BundleValidator().validate_pipes([pipe], library_id=library_id)
            assert results[pipe.pipe_ref].status.is_success
            assert results[pipe.pipe_ref].pipe_ref == f"{_BV_DOMAIN}.echo_topic"
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    async def test_consecutive_sweeps_use_distinct_run_ids(self, mocker: MockerFixture) -> None:
        # Each sweep dry-runs its pipes under a UNIQUE per-sweep pipeline run id (a `dry_run_`-prefixed
        # uuid) threaded into prepare_pipe_job. With the live registry removed (usage rides on PipeOutput),
        # nothing accumulates per-run state, but the per-sweep id stays distinct so each run is individually
        # identifiable. Spy on the REAL prepare_pipe_job (mocker.spy still calls through) and assert the two
        # sweeps used DIFFERENT `dry_run_`-prefixed ids and both classified SUCCESS.
        prepare_spy = mocker.spy(bundle_validator, "prepare_pipe_job")
        library_manager = get_library_manager()
        library_id = "bv_two_sweeps_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            validator = BundleValidator()
            first = await validator.validate_pipes([pipe], library_id=library_id)
            second = await validator.validate_pipes([pipe], library_id=library_id)
            assert first[pipe.pipe_ref].status.is_success
            assert second[pipe.pipe_ref].status.is_success
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

        run_ids = [call.kwargs["pipeline_run_id"] for call in prepare_spy.call_args_list]
        assert len(run_ids) == 2
        assert all(run_id.startswith("dry_run_") for run_id in run_ids)
        assert run_ids[0] != run_ids[1]

    async def test_concurrent_sweeps_run_with_genuine_overlap(self, mocker: MockerFixture) -> None:
        # Two OVERLAPPING sweeps (concurrent `/validate` API requests) must both run to completion and
        # classify SUCCESS. A DRY sweep runs to completion without yielding to the event loop, so `gather`
        # alone would run the two sweeps sequentially and never overlap (in production the overlap comes
        # from yield points elsewhere in the request handler). We force the overlap deterministically: each
        # sweep PARKS inside prepare_pipe_job until both are in flight at once. We release only when two are
        # parked simultaneously and assert the PEAK simultaneous occupancy reached 2 — that is what proves
        # genuine overlap. It is robust to the sweep's pipe count: a sweep blocks on its FIRST prepare (it
        # cannot start a second pipe until the first returns), so each sweep contributes at most one to the
        # count; the gate cannot be tripped by one sweep alone. (Before Phase 4, the sweep keyed a report
        # registry on the process-global ReportingManager, and a constant id made the second sweep collide
        # with "already exists"; the live registry is now gone, so concurrent sweeps share no per-run state
        # at all.) The 5s wait_for is a safety net: if one sweep never reaches prepare (peak stays 1), it
        # times out into a clear failure rather than hanging forever.
        real_prepare = bundle_validator.prepare_pipe_job
        both_parked = asyncio.Event()
        parked = 0
        peak_parked = 0

        async def barrier_prepare(*args: Any, **kwargs: Any) -> Any:
            nonlocal parked, peak_parked
            parked += 1
            peak_parked = max(peak_parked, parked)
            if parked >= 2:
                both_parked.set()
            try:
                await asyncio.wait_for(both_parked.wait(), timeout=5)
            finally:
                parked -= 1
            return await real_prepare(*args, **kwargs)

        mocker.patch.object(bundle_validator, "prepare_pipe_job", side_effect=barrier_prepare)

        library_manager = get_library_manager()
        library_id = "bv_concurrent_sweeps_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            first, second = await asyncio.gather(
                BundleValidator().validate_pipes([pipe], library_id=library_id),
                BundleValidator().validate_pipes([pipe], library_id=library_id),
            )
            assert first[pipe.pipe_ref].status.is_success
            assert second[pipe.pipe_ref].status.is_success
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

        # Proof of genuine overlap: both sweeps were parked inside prepare_pipe_job at the same instant.
        # If they had run sequentially (the failure this test guards against), peak_parked would be 1.
        assert peak_parked == 2

    async def test_cross_package_controller_skipped_not_aborting_sweep(self) -> None:
        # Finding #1 / D7: a controller whose branch references an UNLOADED cross-package sub-pipe
        # raises PipeNotFoundError in the step-1 validate_with_libraries pass. It must be recorded
        # SKIPPED (not abort the sweep), and the sibling implemented leaf must still classify SUCCESS.
        library_manager = get_library_manager()
        library_id = "bv_xpkg_skip_lib"
        acquire_library(library_id=library_id, mthds_contents=[_BV_XPKG_MTHDS])
        try:
            leaf = get_required_pipe(pipe_code=f"{_BV_XPKG_DOMAIN}.implemented_leaf")
            controller = get_required_pipe(pipe_code=f"{_BV_XPKG_DOMAIN}.cross_parallel")
            results = await BundleValidator().validate_pipes([controller, leaf], library_id=library_id)
            assert results[f"{_BV_XPKG_DOMAIN}.cross_parallel"].status == DryRunStatus.SKIPPED
            assert results[f"{_BV_XPKG_DOMAIN}.implemented_leaf"].status.is_success
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    async def test_one_pipe_dry_run_event_and_no_stray_pipeline_events(self, mocker: MockerFixture) -> None:
        library_manager = get_library_manager()
        library_id = "bv_telemetry_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            track_event_spy = mocker.spy(get_telemetry_manager(), "track_event")
            await BundleValidator().validate_pipes([pipe], library_id=library_id)

            emitted_events = [call.kwargs.get("event_name") for call in track_event_spy.call_args_list]
            assert emitted_events.count(EventName.PIPE_DRY_RUN) == 1
            # The sweep never goes through the runner wrapper, so its per-run events must not fire.
            assert EventName.PIPELINE_EXECUTE not in emitted_events
            assert EventName.PIPELINE_COMPLETE not in emitted_events
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()
