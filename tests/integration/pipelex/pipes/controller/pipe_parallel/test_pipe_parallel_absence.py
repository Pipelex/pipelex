"""PipeParallel combine under absence (D11): an absent branch result is absorbed, omitted, or a
typed runtime error — never a crash on the raising main-stuff accessor.

- `Composite` output: the absent component is omitted from the composite, with a ledger note.
- Structured output, non-required field: the absence converts to field-level `None` at the combine
  boundary (taint terminates there).
- Structured output, required field: a typed PipeRunError naming the branch and the field (this is
  statically unreachable once Step D's taint pass lands, but the runtime must not feed
  `combine_stuffs` a hole).

Branches are PipeFuncs; the lifted branch consumes a plain input fed a recorded absence (D3).
"""

from typing import Callable

import pytest
from pydantic import Field

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library, get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_hub import get_class_registry
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_par"


class ParAbsReport(StructuredContent):
    """Combination target with one required and one absorbable (non-required) field."""

    base_result: TextContent = Field(description="Result of the always-running branch")
    found_result: TextContent | None = Field(default=None, description="Result of the maybe-lifted branch")


class ParAbsStrictReport(StructuredContent):
    """Combination target whose fields are all required — no absorption possible."""

    base_result: TextContent = Field(description="Result of the always-running branch")
    found_result: TextContent = Field(description="Result of the maybe-lifted branch")


def optionals_par_echo_source(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"found:{working_memory.get_stuff_as_str(name='source')}")


def optionals_par_echo_topic(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"base:{working_memory.get_stuff_as_str(name='topic')}")


_TEST_FUNCS = [optionals_par_echo_source, optionals_par_echo_topic]


def _make_live_run_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


def _build_parallel(*, output_ref: str, structure_class_names: list[str], add_each_output: bool = False) -> PipeParallel:
    """Register the two branch PipeFuncs and build the parallel over them.

    Branch 'found_result' consumes `source` plain — lifted when source is absent-with-record.
    Branch 'base_result' consumes `topic` — always runs. The parallel declares `source` optional
    at its own boundary so it runs (its branch lifts) instead of lifting wholesale.
    """
    branch_found = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_par_find",
        blueprint=PipeFuncBlueprint(
            description="Consumes the maybe-absent source (plain input): lifted when source is absent",
            inputs={"source": "Text"},
            output="Text",
            function_name="optionals_par_echo_source",
        ),
    )
    branch_base = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_par_base",
        blueprint=PipeFuncBlueprint(
            description="Consumes the always-present topic",
            inputs={"topic": "Text"},
            output="Text",
            function_name="optionals_par_echo_topic",
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [branch_found, branch_base]:
        pipe_library.add_new_pipe(pipe=pipe)

    for structure_class_name in structure_class_names:
        concept = ConceptFactory.make(
            concept_code=structure_class_name,
            domain_code=_DOMAIN_CODE,
            description=f"Test combination concept {structure_class_name}",
            structure_class_name=structure_class_name,
        )
        get_concept_library().add_new_concept(concept=concept)

    parallel = PipeFactory[PipeParallel].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_par_combine",
        blueprint=PipeParallelBlueprint(
            description="Parallel over a maybe-lifted branch and an always-running branch",
            inputs={"source": "Text?", "topic": "Text"},
            output=output_ref,
            branches=[
                SubPipeBlueprint(pipe="opt_par_find", result="found_result"),
                SubPipeBlueprint(pipe="opt_par_base", result="base_result"),
            ],
            add_each_output=add_each_output,
        ),
        concept_codes_from_the_same_domain=structure_class_names,
    )
    pipe_library.add_new_pipe(pipe=parallel)
    return parallel


def _make_absent_source_memory() -> WorkingMemory:
    working_memory = WorkingMemoryFactory.make_from_single_stuff(StuffFactory.make_from_str("penalties", name="topic"))
    working_memory.record_absence(
        AbsenceRecord(
            variable_name="source",
            kind=AbsenceKind.DECLARED_ABSENT,
            reason="no penalty clause found in this contract",
            producing_pipe="extract_penalty_clause",
        ),
    )
    return working_memory


@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelAbsence:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)
        get_class_registry().register_class(ParAbsReport)
        get_class_registry().register_class(ParAbsStrictReport)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_composite_output_omits_absent_component_with_ledger_note(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Composite output: the absent component is omitted; a ledger note keeps observability."""
        load_empty_library()
        parallel = _build_parallel(output_ref="Composite", structure_class_names=[], add_each_output=True)
        working_memory = _make_absent_source_memory()

        pipe_output = await parallel.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        main_stuff = pipe_output.main_stuff
        assert isinstance(main_stuff.content, CompositeContent)
        assert set(main_stuff.content.components.keys()) == {"base_result"}

        result_memory = pipe_output.working_memory
        # add_each_output: the present branch is exposed by name; the absent one is a ledger note.
        base_stuff = result_memory.get_optional_stuff("base_result")
        assert base_stuff is not None
        assert base_stuff.as_text.text == "base:penalties"
        assert result_memory.get_optional_stuff("found_result") is None
        note = result_memory.get_optional_absence("found_result")
        assert note is not None
        assert note.kind == AbsenceKind.SKIPPED
        assert note.producing_pipe == "opt_par_find"
        assert note.origin().producing_pipe == "extract_penalty_clause"
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id

    async def test_structured_output_optional_field_absorbs_as_none(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Structured output: a non-required field absorbs the absent branch as field-level None."""
        load_empty_library()
        parallel = _build_parallel(output_ref=f"{_DOMAIN_CODE}.ParAbsReport", structure_class_names=["ParAbsReport", "ParAbsStrictReport"])
        working_memory = _make_absent_source_memory()

        pipe_output = await parallel.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        main_stuff = pipe_output.main_stuff
        combined = main_stuff.content
        assert isinstance(combined, ParAbsReport)
        assert combined.found_result is None
        assert combined.base_result.text == "base:penalties"
        # The taint terminates at the combine boundary: the combined output is a real value.
        assert isinstance(pipe_output.working_memory.resolve_main_stuff(), Stuff)

    async def test_structured_output_required_field_fed_absent_branch_raises(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Structured output: a required field fed an absent branch is a typed runtime error that
        names the branch and the field — never a hole handed to combine_stuffs.
        """
        load_empty_library()
        parallel = _build_parallel(output_ref=f"{_DOMAIN_CODE}.ParAbsStrictReport", structure_class_names=["ParAbsReport", "ParAbsStrictReport"])
        working_memory = _make_absent_source_memory()

        with pytest.raises(PipeRunError) as exc_info:
            await parallel.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=_make_live_run_params(),
            )
        message = str(exc_info.value)
        assert "opt_par_find" in message
        assert "found_result" in message

    async def test_absent_branch_without_add_each_output_leaves_parent_slot_untouched(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]
    ):
        """Without add_each_output, branch result names are not parent slots: an absent branch must
        not clobber an unrelated same-named value in the parent memory (present branches don't).
        """
        load_empty_library()
        parallel = _build_parallel(output_ref="Composite", structure_class_names=[], add_each_output=False)
        working_memory = _make_absent_source_memory()
        working_memory.add_new_stuff(name="found_result", stuff=StuffFactory.make_from_str("pre-existing unrelated value", name="found_result"))

        pipe_output = await parallel.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        main_stuff = pipe_output.main_stuff
        assert isinstance(main_stuff.content, CompositeContent)
        assert set(main_stuff.content.components.keys()) == {"base_result"}

        result_memory = pipe_output.working_memory
        surviving = result_memory.get_optional_stuff("found_result")
        assert surviving is not None
        assert surviving.as_text.text == "pre-existing unrelated value"
        assert result_memory.get_optional_absence("found_result") is None

    async def test_all_branches_present_combines_as_before(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """With every branch present, the combine is byte-for-byte the pre-optionals behavior."""
        load_empty_library()
        parallel = _build_parallel(output_ref=f"{_DOMAIN_CODE}.ParAbsReport", structure_class_names=["ParAbsReport", "ParAbsStrictReport"])
        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            [
                StuffFactory.make_from_str("clause 12", name="source"),
                StuffFactory.make_from_str("penalties", name="topic"),
            ],
        )

        pipe_output = await parallel.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        combined = pipe_output.main_stuff.content
        assert isinstance(combined, ParAbsReport)
        assert combined.found_result is not None
        assert combined.found_result.text == "found:clause 12"
        assert combined.base_result.text == "base:penalties"
