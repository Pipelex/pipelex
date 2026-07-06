"""Optional method inputs (D5): omitting a `?` input from the pipeline inputs yields a
not-provided absence record instead of an error; the required-input error message tells the
caller which optional inputs may legitimately be omitted; mock seeding stays all-present (D6).
"""

from typing import Callable

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs

from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.execution_seams import prepare_pipe_job
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry


def optionals_method_report(working_memory: WorkingMemory) -> TextContent:
    topic = working_memory.get_stuff_as_str(name="topic")
    source_stuff = working_memory.get_optional_stuff(name="source")
    if source_stuff is None:
        return TextContent(text=f"report about {topic} (no source)")
    return TextContent(text=f"report about {topic} from {source_stuff.as_text.text}")


def _make_method_pipe() -> PipeFunc:
    return PipeFactory[PipeFunc].make_from_blueprint(
        domain_code="test_optionals_method",
        pipe_code="opt_method_report",
        blueprint=PipeFuncBlueprint(
            description="Method with a required topic and an optional source",
            inputs={"topic": "Text", "source": "Text?"},
            output="Text",
            function_name="optionals_method_report",
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestOptionalMethodInputs:
    @classmethod
    def setup_class(cls):
        func_registry.register_function(optionals_method_report)

    @classmethod
    def teardown_class(cls):
        if func_registry.has_function("optionals_method_report"):
            func_registry.unregister_function_by_name("optionals_method_report")

    async def test_omitted_optional_input_records_not_provided(self, load_empty_library: Callable[[], str]):
        """prepare_pipe_job seeds a not-provided absence record for each omitted `?` input."""
        library_id = load_empty_library()
        pipe = _make_method_pipe()
        execution_config = get_config().pipelex.pipeline_execution_config

        pipe_job = await prepare_pipe_job(
            pipe=pipe,
            library_id=library_id,
            execution_config=execution_config,
            pipe_run_mode=PipeRunMode.LIVE,
            pipeline_run_id="test-optional-method-inputs",
            user_id="pytest",
            inputs=PipelineInputs({"topic": "penalties"}),
        )

        job_memory = pipe_job.working_memory
        assert job_memory is not None
        record = job_memory.get_optional_absence("source")
        assert record is not None
        assert record.kind == AbsenceKind.NOT_PROVIDED
        assert record.producing_pipe is None
        assert "source" in record.reason
        # The pipe then runs on the absent arm without error.
        pipe_output = await pipe.run_pipe(
            job_metadata=pipe_job.job_metadata,
            working_memory=job_memory,
            pipe_run_params=pipe_job.pipe_run_params,
        )
        assert pipe_output.main_stuff.as_text.text == "report about penalties (no source)"

    async def test_provided_optional_input_leaves_no_record(self, load_empty_library: Callable[[], str]):
        library_id = load_empty_library()
        pipe = _make_method_pipe()
        execution_config = get_config().pipelex.pipeline_execution_config

        pipe_job = await prepare_pipe_job(
            pipe=pipe,
            library_id=library_id,
            execution_config=execution_config,
            pipe_run_mode=PipeRunMode.LIVE,
            pipeline_run_id="test-optional-method-inputs-provided",
            user_id="pytest",
            inputs=PipelineInputs({"topic": "penalties", "source": "clause 12"}),
        )

        job_memory = pipe_job.working_memory
        assert job_memory is not None
        assert job_memory.get_optional_absence("source") is None
        assert job_memory.get_optional_stuff("source") is not None

    async def test_preexisting_absence_record_keeps_its_provenance(self, load_empty_library: Callable[[], str]):
        """A caller-provided WorkingMemory whose `?` slot already resolved as a recorded absence
        (e.g. a previous run's output chained in) keeps that record — prepare_pipe_job must not
        downgrade it to a fresh not-provided.
        """
        library_id = load_empty_library()
        pipe = _make_method_pipe()
        execution_config = get_config().pipelex.pipeline_execution_config

        chained_memory = WorkingMemoryFactory.make_from_single_stuff(StuffFactory.make_from_str("penalties", name="topic"))
        upstream_record = AbsenceRecord(
            variable_name="source",
            kind=AbsenceKind.SKIPPED,
            reason="skipped because input 'clause' is absent",
            producing_pipe="extract_source",
        )
        chained_memory.record_absence(upstream_record)

        pipe_job = await prepare_pipe_job(
            pipe=pipe,
            library_id=library_id,
            execution_config=execution_config,
            pipe_run_mode=PipeRunMode.LIVE,
            pipeline_run_id="test-optional-method-inputs-chained",
            user_id="pytest",
            inputs=chained_memory,
        )

        job_memory = pipe_job.working_memory
        assert job_memory is not None
        record = job_memory.get_optional_absence("source")
        assert record is not None
        assert record.kind == AbsenceKind.SKIPPED
        assert record.producing_pipe == "extract_source"
        assert record.reason == "skipped because input 'clause' is absent"

    async def test_missing_required_error_hints_omittable_optionals(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Omitting a required input still fails, but the message now names the optional inputs
        that may legitimately be omitted.
        """
        load_empty_library()
        pipe = _make_method_pipe()
        run_params = PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)

        with pytest.raises(PipeRunInputsError) as exc_info:
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=run_params,
            )
        message = str(exc_info.value)
        assert "topic" in message
        assert "optional" in message.lower()
        assert "source" in message

    async def test_mock_inputs_seed_optional_slots_all_present(self, load_empty_library: Callable[[], str]):
        """Dry-run mock seeding stays all-present (D6): optional inputs get mocks, no records."""
        library_id = load_empty_library()
        pipe = _make_method_pipe()
        execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=False,
            mock_inputs=True,
        )

        pipe_job = await prepare_pipe_job(
            pipe=pipe,
            library_id=library_id,
            execution_config=execution_config,
            pipe_run_mode=PipeRunMode.DRY,
            pipeline_run_id="test-optional-method-inputs-mocked",
            user_id="pytest",
        )

        job_memory = pipe_job.working_memory
        assert job_memory is not None
        assert job_memory.get_optional_stuff("source") is not None
        assert job_memory.get_optional_stuff("topic") is not None
        assert job_memory.get_optional_absence("source") is None
