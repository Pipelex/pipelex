"""D11 static rule: a REQUIRED structure field fed by a maybe-absent branch is a validation error
(extends `PipeParallel.validate_output_with_library`). A branch is maybe-absent when its pipe is
liftable inside the parallel (plain input fed by the parallel's `?` input) or when it declares a
`?` output. Non-required fields absorb (field-level None); `Composite` omits the component.
"""

from typing import Callable

import pytest
from pydantic import Field

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library, get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.runtime_hub import get_class_registry
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_par_static"


class ParTaintReport(StructuredContent):
    """Combination target with one required and one absorbable (non-required) field."""

    base_result: TextContent = Field(description="Result of the always-guaranteed branch")
    found_result: TextContent | None = Field(default=None, description="Result of the maybe-absent branch")


class ParTaintStrictReport(StructuredContent):
    """Combination target whose fields are all required — no absorption possible."""

    base_result: TextContent = Field(description="Result of the always-guaranteed branch")
    found_result: TextContent = Field(description="Result of the maybe-absent branch")


def optionals_par_static_find(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"found:{working_memory.get_stuff_as_str(name='source')}")


def optionals_par_static_base(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"base:{working_memory.get_stuff_as_str(name='topic')}")


_TEST_FUNCS = [optionals_par_static_find, optionals_par_static_base]


def _register_branch_pipes(*, find_output_ref: str = "Text") -> None:
    branch_found = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="par_static_find",
        blueprint=PipeFuncBlueprint(
            description="Consumes source plain: liftable when the parallel's source is optional",
            inputs={"source": "Text"},
            output=find_output_ref,
            function_name="optionals_par_static_find",
        ),
    )
    branch_base = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="par_static_base",
        blueprint=PipeFuncBlueprint(
            description="Consumes the always-present topic",
            inputs={"topic": "Text"},
            output="Text",
            function_name="optionals_par_static_base",
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [branch_found, branch_base]:
        pipe_library.add_new_pipe(pipe=pipe)


def _build_parallel(*, output_ref: str, structure_class_names: list[str], inputs: dict[str, str]) -> PipeParallel:
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
        pipe_code="par_static_combine",
        blueprint=PipeParallelBlueprint(
            description="Parallel over a maybe-absent branch and a guaranteed branch",
            inputs=inputs,
            output=output_ref,
            branches=[
                SubPipeBlueprint(pipe="par_static_find", result="found_result"),
                SubPipeBlueprint(pipe="par_static_base", result="base_result"),
            ],
            add_each_output=False,
        ),
        concept_codes_from_the_same_domain=structure_class_names,
    )
    get_pipe_library().add_new_pipe(pipe=parallel)
    return parallel


class TestParallelOptionalCombineValidation:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)
        get_class_registry().register_class(ParTaintReport)
        get_class_registry().register_class(ParTaintStrictReport)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    def test_required_field_fed_by_liftable_branch_is_rejected(self, load_empty_library: Callable[[], str]):
        """The parallel's `?` input makes the find branch liftable, and 'found_result' is required."""
        load_empty_library()
        _register_branch_pipes()
        parallel = _build_parallel(
            output_ref="ParTaintStrictReport",
            structure_class_names=["ParTaintStrictReport"],
            inputs={"source": "Text?", "topic": "Text"},
        )

        with pytest.raises(PipeValidationError) as exc_info:
            parallel.validate_with_libraries()
        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
        assert "found_result" in str(error)
        assert "par_static_find" in str(error)

    def test_required_field_fed_by_optional_output_branch_is_rejected(self, load_empty_library: Callable[[], str]):
        """A branch declaring a `?` output is maybe-absent even with all-plain parallel inputs."""
        load_empty_library()
        _register_branch_pipes(find_output_ref="Text?")
        parallel = _build_parallel(
            output_ref="ParTaintStrictReport",
            structure_class_names=["ParTaintStrictReport"],
            inputs={"source": "Text", "topic": "Text"},
        )

        with pytest.raises(PipeValidationError) as exc_info:
            parallel.validate_with_libraries()
        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD

    def test_non_required_field_absorbs_the_maybe_absent_branch(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_branch_pipes()
        parallel = _build_parallel(
            output_ref="ParTaintReport",
            structure_class_names=["ParTaintReport"],
            inputs={"source": "Text?", "topic": "Text"},
        )
        parallel.validate_with_libraries()

    def test_composite_output_accepts_maybe_absent_branches(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_branch_pipes()
        parallel = _build_parallel(
            output_ref="Composite",
            structure_class_names=[],
            inputs={"source": "Text?", "topic": "Text"},
        )
        parallel.validate_with_libraries()

    def test_all_plain_inputs_keep_todays_rules(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_branch_pipes()
        parallel = _build_parallel(
            output_ref="ParTaintStrictReport",
            structure_class_names=["ParTaintStrictReport"],
            inputs={"source": "Text", "topic": "Text"},
        )
        parallel.validate_with_libraries()
