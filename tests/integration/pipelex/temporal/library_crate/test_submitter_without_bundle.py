"""Integration test for submitter-side rehydration without bundle pre-loaded.

Validates that `rehydrate_pipe_output_with_crate` succeeds against an empty
submitter-side global registry by spinning up its own per-call scoped library
from the `LibraryCrate` carried by the `PipeJob`.

This is the production guarantee for remote API clients that built the
`PipeJob` from a serialized `LibraryCrate` and never loaded the bundle into
their global `KajsonManager` registry.
"""

import uuid
from collections.abc import Generator

import pytest
from kajson.kajson_manager import KajsonManager
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.hub import clear_current_library, get_current_library, set_current_library
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.runtime_bridge.primitives.submitter_hydration import rehydrate_pipe_output_with_crate
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.test_data import DeferredHydrationTestData

GREETING_CLASS_NAME = f"{DeferredHydrationTestData.DOMAIN}__Greeting"


def _current_library_id_or_none() -> str | None:
    """Read current_library without raising when none is set."""
    try:
        return get_current_library()
    except RuntimeError:
        return None


@pytest.fixture(scope="class")
def pipe_job_isolated_dynamic_concept() -> Generator[PipeJob, None, None]:
    """PipeJob built from the dynamic-concept bundle with a scoped (isolated) ClassRegistry.

    Forces ``isolated_registry=True`` so the dynamic Greeting class lands in
    the fixture's scoped registry and the global ``KajsonManager`` registry
    stays clean — the precondition for the "submitter without bundle
    pre-loaded" scenario this module exercises.
    """
    yield from pipe_job_from_bundle(
        bundle_file=DeferredHydrationTestData.BUNDLE_FILE,
        pipe_code=DeferredHydrationTestData.PIPE_CODE,
        isolated_registry=True,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestSubmitterWithoutBundleLoaded:
    async def _dispatch_and_get_deferred_pipe_output(
        self,
        pipe_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> PipeOutput:
        """Run the workflow and return the PipeOutput as-received (with working_memory_raw populated)."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=pipe_job,
                id=workflow_id,
                task_queue=task_queue,
            )

        assert isinstance(pipe_output, PipeOutput)
        assert pipe_output.working_memory_raw is not None, "Worker should have returned a deferred PipeOutput (working_memory_raw populated)"
        return pipe_output

    async def test_helper_rehydrates_with_clean_global_registry(
        self,
        pipe_job_isolated_dynamic_concept: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """rehydrate_pipe_output_with_crate succeeds when the submitter never loaded the bundle.

        The fixture runs in isolated-registry mode, so the dynamic Greeting class
        lives only in the fixture's scoped library, never in the global registry.
        We additionally clear the current_library ContextVar before calling the
        helper so the active class registry falls back to the (clean) global —
        which simulates a remote submitter that received the PipeJob+crate over
        the wire and never touched a Pipelex library at all.
        """
        pipe_output = await self._dispatch_and_get_deferred_pipe_output(
            pipe_job_isolated_dynamic_concept,
            temporal_client,
        )

        global_registry = KajsonManager.get_class_registry()
        assert global_registry.get_class(name=GREETING_CLASS_NAME) is None, (
            f"Precondition violated: '{GREETING_CLASS_NAME}' is in the global KajsonManager registry; "
            "the test cannot prove the submitter-without-bundle path."
        )

        previous_library_id = _current_library_id_or_none()
        clear_current_library()
        try:
            rehydrated = rehydrate_pipe_output_with_crate(
                pipe_output,
                library_crate=pipe_job_isolated_dynamic_concept.library_crate,
            )

            assert rehydrated is pipe_output, "Helper should mutate in place and return the same instance"
            assert rehydrated.working_memory_raw is None, "working_memory_raw should be cleared after rehydration"

            greeting_stuff = rehydrated.working_memory.get_stuff("greeting_result")
            assert isinstance(greeting_stuff.content, StructuredContent), (
                f"Expected StructuredContent for 'greeting_result' after rehydration, got {type(greeting_stuff.content).__name__}"
            )
            assert hasattr(greeting_stuff.content, "message"), "Hydrated Greeting should have 'message' field"
            assert hasattr(greeting_stuff.content, "language"), "Hydrated Greeting should have 'language' field"

            assert global_registry.get_class(name=GREETING_CLASS_NAME) is None, (
                f"Helper leaked '{GREETING_CLASS_NAME}' into the global KajsonManager registry"
            )
            assert _current_library_id_or_none() is None, "Helper should have restored the previous (None) current_library after teardown"
        finally:
            if previous_library_id is not None:
                set_current_library(library_id=previous_library_id)

    async def test_no_crate_path_fails_without_bundle(
        self,
        pipe_job_isolated_dynamic_concept: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Counterpart: rehydrating without the crate fails when the submitter has no bundle.

        Demonstrates the exact silent-failure surface the helper closes — a
        plain `hydrate_working_memory` call against a clean global registry
        cannot resolve the dynamic Greeting class. The new helper avoids this
        by opening a per-call scoped library from the crate.
        """
        pipe_output = await self._dispatch_and_get_deferred_pipe_output(
            pipe_job_isolated_dynamic_concept,
            temporal_client,
        )
        assert pipe_output.working_memory_raw is not None

        previous_library_id = _current_library_id_or_none()
        clear_current_library()
        try:
            with pytest.raises(PipeJobError):
                hydrate_working_memory(pipe_output.working_memory_raw)
        finally:
            if previous_library_id is not None:
                set_current_library(library_id=previous_library_id)

    async def test_repeated_rehydrations_do_not_leak(
        self,
        pipe_job_isolated_dynamic_concept: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Repeated back-to-back submitter rehydrations leave no residual state.

        Dispatches one workflow, then invokes the helper twice in sequence on
        independent copies of the deferred PipeOutput. Catches per-call
        scoped-library leaks (open libraries piling up, dynamic classes
        bleeding into the global registry, current_library not restored).
        Sequential rather than `asyncio.gather`-parallel because the helper
        is synchronous — gathering it would only run sequentially anyway.
        """
        pipe_output_template = await self._dispatch_and_get_deferred_pipe_output(
            pipe_job_isolated_dynamic_concept,
            temporal_client,
        )
        raw_payload = pipe_output_template.working_memory_raw
        assert raw_payload is not None

        global_registry = KajsonManager.get_class_registry()
        assert global_registry.get_class(name=GREETING_CLASS_NAME) is None

        previous_library_id = _current_library_id_or_none()
        clear_current_library()
        try:
            crate = pipe_job_isolated_dynamic_concept.library_crate
            for _index in range(2):
                pipe_output = pipe_output_template.model_copy(update={"working_memory_raw": dict(raw_payload)})
                rehydrated = rehydrate_pipe_output_with_crate(pipe_output, library_crate=crate)
                greeting_stuff = rehydrated.working_memory.get_stuff("greeting_result")
                assert isinstance(greeting_stuff.content, StructuredContent)
                assert hasattr(greeting_stuff.content, "message")
                assert hasattr(greeting_stuff.content, "language")
                assert _current_library_id_or_none() is None, "Helper should leave current_library back at None after each call"
                assert global_registry.get_class(name=GREETING_CLASS_NAME) is None, (
                    f"Iteration leaked '{GREETING_CLASS_NAME}' into the global KajsonManager registry"
                )
        finally:
            if previous_library_id is not None:
                set_current_library(library_id=previous_library_id)
