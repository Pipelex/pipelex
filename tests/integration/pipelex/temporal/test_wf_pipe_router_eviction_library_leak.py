"""Regression guard for the eviction-time library leak that poisons same-worker replay in ``WfPipeRouter``.

The bug (finding H2 in ``wip/distributed-execution/workflow-nondeterminism-audit.md``): the
worker-local library teardown sits in the workflow's ``finally`` block AFTER the awaited
``act_flush_trace_events`` activity. An eviction-time interruption raised at that await
(``_WorkflowBeingEvictedError`` is a ``BaseException``) bypasses the ``except Exception``
around the flush and aborts the rest of the ``finally``: the per-workflow library and its
crate fingerprint leak in the worker-local ``LibraryManager`` singleton, keyed by the
*deterministic* ``wf_{workflow_id}``. When the same worker then replays or re-runs that
workflow, ``open_library`` returns the stale library, ``set_class_registry`` installs a
FRESH registry seeded only from the global one, and ``load_from_crate`` is
fingerprint-skipped — so the crate's dynamic classes are never registered into the new
registry and inline hydration fails where history recorded success: command-stream
divergence, and with dynamic-class activity results on a single-worker queue, a persistent
silent hang.

How the reproduction works:

Forcing a real eviction exactly during the flush await is racy, so the test installs the
*post-eviction leaked state* directly: it performs the same setup steps the interrupted
predecessor execution would have performed — open the library under ``wf_{workflow_id}``,
attach a scoped class registry, ``load_from_crate`` — and deliberately skips teardown,
leaving the library and the crate fingerprint behind in the ``LibraryManager``. It then
runs ``WfPipeRouter`` with that exact workflow id and a payload whose
``working_memory_raw`` carries a dynamic-concept stuff (the deferred-hydration path).
With the bug, the fingerprint skip leaves the dynamic class unregistered in the fresh
per-workflow registry and the workflow fails inline at hydration. The test asserts the
workflow completes and hydrates correctly: RED while the bug is present (TDD).

The job is built with an isolated class registry on purpose: in shared mode the dynamic
classes also live in the global registry, the workflow's fresh per-workflow registry
inherits them on seeding, and the leak is masked.

Fix shape: make the per-workflow library setup self-healing against a leaked predecessor
under the same deterministic id — scope the fingerprint dedup to the registry instance,
or force-teardown any pre-existing library before opening — and additionally make the
``finally`` cleanup eviction-safe.
"""

import uuid
from collections.abc import Generator
from contextlib import suppress
from datetime import timedelta

import pytest
from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from temporalio.client import Client as TemporalClient

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.hub import get_current_library, get_library_manager, get_required_concept, set_current_library
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.test_data import DeferredHydrationTestData


@pytest.fixture(scope="class")
def isolated_hydration_job() -> Generator[PipeJob, None, None]:
    """PipeJob from the dynamic-concept bundle with a library-scoped class registry.

    Isolation is required for the reproduction (not parametrized on purpose): with the
    shared registry the workflow's per-workflow registry inherits the dynamic classes
    from the global one and the fingerprint-skip bug cannot manifest.
    """
    yield from pipe_job_from_bundle(
        bundle_file=DeferredHydrationTestData.BUNDLE_FILE,
        pipe_code=DeferredHydrationTestData.PIPE_CODE,
        isolated_registry=True,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterEvictionLibraryLeak:
    async def test_workflow_recovers_from_leaked_predecessor_library(
        self,
        temporal_client: TemporalClient,
        isolated_hydration_job: PipeJob,
    ) -> None:
        """A leaked predecessor library under the same ``wf_{workflow_id}`` must not poison the run.

        With the bug, ``load_from_crate`` is fingerprint-skipped against the leaked
        library while ``set_class_registry`` already swapped in a fresh registry, so
        deferred hydration of the dynamic Greeting stuff fails inline and the workflow
        fails terminally instead of completing.
        """
        # Build an input WorkingMemory carrying a dynamic-concept stuff, then dehydrate it
        # for Temporal transit so the workflow must hydrate it inline after crate loading.
        greeting_concept = get_required_concept(concept_ref=f"{DeferredHydrationTestData.DOMAIN}.Greeting")
        greeting_content = StuffContentFactory.make_stuff_content_from_concept_required(
            concept=greeting_concept,
            value={"message": "Bonjour le monde", "language": "French"},
        )
        greeting_stuff = Stuff(
            stuff_code="leak_input",
            stuff_name="greeting_result",
            concept=greeting_concept,
            content=greeting_content,
        )
        input_memory = WorkingMemory()
        input_memory.root["greeting_result"] = greeting_stuff
        prepared_job = isolated_hydration_job.model_copy(update={"working_memory": input_memory}).prepare_for_temporal()
        assert prepared_job.working_memory_raw is not None, "prepare_for_temporal must populate working_memory_raw"
        library_crate = prepared_job.library_crate
        assert library_crate is not None, "the dynamic-concept job must carry a library crate"

        workflow_id = f"wf_eviction_leak_{uuid.uuid4().hex[:8]}"
        leaked_library_id = f"wf_{workflow_id}"

        # Install the post-eviction leaked state: replay the interrupted predecessor's
        # setup steps (mirroring WfPipeRouter.run) and deliberately skip teardown, so the
        # library AND the crate fingerprint stay behind in the worker-local LibraryManager.
        library_manager = get_library_manager()
        fixture_library_id = get_current_library()
        global_registry = KajsonManager.get_class_registry()
        predecessor_registry = ClassRegistry()
        predecessor_registry.register_classes_dict(global_registry.get_classes_dict())
        _opened_library_id, leaked_library = library_manager.open_library(library_id=leaked_library_id)
        leaked_library.set_class_registry(predecessor_registry)
        set_current_library(library_id=leaked_library_id)
        try:
            library_manager.load_from_crate(library_id=leaked_library_id, crate=library_crate)
        finally:
            set_current_library(library_id=fixture_library_id)

        task_queue = f"q_eviction_leak_{uuid.uuid4().hex[:8]}"
        try:
            async with get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
            ):
                # With the bug this raises WorkflowFailureError: the inline hydration
                # failure is converted to a terminal TemporalError by the workflow's
                # fail-safe floor. The execution timeout is a safety net in case a
                # regression turns the inline failure into a workflow-task retry loop.
                pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                    workflow=WfPipeRouter.run,
                    arg=prepared_job,
                    id=workflow_id,
                    task_queue=task_queue,
                    execution_timeout=timedelta(seconds=60),
                )
        finally:
            # The workflow's own finally tears the library down on most paths; suppress
            # covers early failures so the leak never escapes into other tests.
            with suppress(LibraryError):
                library_manager.teardown(library_id=leaked_library_id)

        assert isinstance(pipe_output, PipeOutput)
        rehydrate_pipe_output(pipe_output)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        # The hydrated dynamic-concept input must have survived the full round-trip.
        assert working_memory.is_stuff_exists("greeting_result"), "greeting_result should be in output WM"
        greeting_out = working_memory.get_stuff("greeting_result")
        assert isinstance(greeting_out.content, StructuredContent), (
            f"Expected StructuredContent after hydration, got {type(greeting_out.content).__name__}"
        )
        assert working_memory.is_stuff_exists("summary_result"), "summary_result should be in output WM"
