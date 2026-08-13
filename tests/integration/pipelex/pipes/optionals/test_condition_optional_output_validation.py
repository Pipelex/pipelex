"""PipeCondition static optionality rules (D5/D6):

- `OPTIONAL_OUTPUT_REQUIRED`: a `continue`-reachable condition (any outcome mapped to `continue`,
  or `default_outcome = "continue"`) MUST declare its output optional — `continue` resolves the
  declared output absent (Step C), so a plain output would hide the no-output path.
- Condition boundary taint: a mapped pipe with a `?` output makes the condition's own output
  maybe-absent, so the condition must declare `?` too (`OPTIONAL_NOT_HANDLED`).
"""

from typing import Callable

import pytest
from pydantic import ValidationError

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.mthds_parsing.handle_pipe_errors import extract_wrapped_pipe_validation_error
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_cond"


def optionals_cond_echo_topic(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"echo:{working_memory.get_stuff_as_str(name='topic')}")


_TEST_FUNCS = [optionals_cond_echo_topic]


def _make_condition(*, output_ref: str, outcomes: dict[str, str], default_outcome: str) -> PipeCondition:
    return PipeFactory[PipeCondition].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_condition",
        blueprint=PipeConditionBlueprint(
            description="Condition under optionality rules",
            inputs={"topic": "Text"},
            output=output_ref,
            expression="topic",
            outcomes=outcomes,
            default_outcome=default_outcome,
        ),
    )


def _register_target_pipe(*, pipe_code: str, output_ref: str) -> None:
    target = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code=pipe_code,
        blueprint=PipeFuncBlueprint(
            description="Mapped target pipe",
            inputs={"topic": "Text"},
            output=output_ref,
            function_name="optionals_cond_echo_topic",
        ),
    )
    get_pipe_library().add_new_pipe(pipe=target)


class TestConditionOptionalOutputValidation:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    # ---- OPTIONAL_OUTPUT_REQUIRED (static, at pipe construction) ----

    def test_continue_outcome_with_plain_output_is_rejected(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            _make_condition(output_ref="Text", outcomes={"skip": "continue", "go": "target_pipe"}, default_outcome="fail")
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED

    def test_continue_default_outcome_with_plain_output_is_rejected(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            _make_condition(output_ref="Text", outcomes={"go": "test_optionals_cond.target_pipe"}, default_outcome="continue")
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED

    def test_continue_with_optional_output_is_accepted(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        condition = _make_condition(output_ref="Text?", outcomes={"skip": "continue", "go": "target_pipe"}, default_outcome="fail")
        assert condition.output.presence.is_optional

    def test_no_continue_with_plain_output_is_accepted(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        condition = _make_condition(output_ref="Text", outcomes={"go": "test_optionals_cond.target_pipe"}, default_outcome="fail")
        assert condition.output.presence.is_plain

    # ---- Condition boundary taint (with library) ----

    def test_mapped_pipe_with_optional_output_requires_optional_condition_output(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_target_pipe(pipe_code="maybe_target", output_ref="Text?")
        condition = _make_condition(output_ref="Text", outcomes={"go": "test_optionals_cond.maybe_target"}, default_outcome="fail")
        get_pipe_library().add_new_pipe(pipe=condition)

        with pytest.raises(PipeValidationError) as exc_info:
            condition.validate_with_libraries()
        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert "maybe_target" in str(exc_info.value)

    def test_mapped_optional_output_accepted_when_condition_output_is_optional(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_target_pipe(pipe_code="maybe_target", output_ref="Text?")
        condition = _make_condition(output_ref="Text?", outcomes={"go": "test_optionals_cond.maybe_target"}, default_outcome="fail")
        get_pipe_library().add_new_pipe(pipe=condition)
        condition.validate_with_libraries()

    def test_mapped_plain_outputs_keep_todays_rules(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_target_pipe(pipe_code="plain_target", output_ref="Text")
        condition = _make_condition(output_ref="Text", outcomes={"go": "test_optionals_cond.plain_target"}, default_outcome="fail")
        get_pipe_library().add_new_pipe(pipe=condition)
        condition.validate_with_libraries()
