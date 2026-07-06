"""Template guard-lint (D7): every template reference to a declared-optional input must be
guarded (`{% if var %}` block, inline `is defined` conditional, or `@?var`). An unguarded
reference is a typed validation error (`OPTIONAL_INPUT_UNGUARDED`) with the precise fix.
Covers PipeLLM prompts/system prompts, PipeCondition expressions, and PipeCompose templates.
"""

from typing import Callable

import pytest
from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.core.pipes.handle_pipe_errors import extract_wrapped_pipe_validation_error
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint

_DOMAIN_CODE = "test_optionals_guard_lint"


def _make_pipe_llm(*, prompt: str, system_prompt: str | None = None) -> PipeLLM:
    return PipeFactory[PipeLLM].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="guard_lint_llm",
        blueprint=PipeLLMBlueprint(
            description="Guard-lint test pipe",
            inputs={"contract": "Text", "assessment": "Text?"},
            output="Text",
            prompt=prompt,
            system_prompt=system_prompt,
        ),
    )


class TestOptionalGuardLint:
    # ---- PipeLLM prompts ----

    @pytest.mark.parametrize(
        ("topic", "prompt"),
        [
            ("at_optional_sigil", "Write a report.\n@contract\n@?assessment"),
            ("if_block", "Write a report.\n@contract\n{% if assessment %}Consider: {{ assessment }}{% endif %}"),
            ("if_defined_block", "Write a report.\n@contract\n{% if assessment is defined %}{{ assessment }}{% endif %}"),
            ("inline_cond", "Report ({{ 'with assessment' if assessment is defined else 'no assessment' }}).\n@contract"),
        ],
    )
    def test_guarded_prompts_are_accepted(self, topic: str, prompt: str, load_empty_library: Callable[[], None]):
        load_empty_library()
        pipe_llm = _make_pipe_llm(prompt=prompt)
        assert pipe_llm.code == "guard_lint_llm", f"{topic}: construction should pass the lint"

    @pytest.mark.parametrize(
        ("topic", "prompt"),
        [
            ("bare_interpolation", "Write a report.\n@contract\n{{ assessment }}"),
            ("deep_access", "Write a report.\n@contract\n{{ assessment.amount }}"),
            ("plain_at_sigil_on_optional", "Write a report.\n@contract\n@assessment"),
            ("else_branch_use", "@contract\n{% if assessment %}x{% else %}{{ assessment }}{% endif %}"),
        ],
    )
    def test_unguarded_prompts_are_rejected(self, topic: str, prompt: str, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            _make_pipe_llm(prompt=prompt)
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None, f"{topic}: expected a wrapped PipeValidationError"
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
        assert "assessment" in str(wrapped)
        # The fix is named precisely.
        assert "@?assessment" in str(wrapped) or "{% if assessment %}" in str(wrapped)

    def test_unguarded_system_prompt_is_rejected(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            _make_pipe_llm(prompt="Write a report.\n@contract\n@?assessment", system_prompt="You know: {{ assessment }}")
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED

    def test_unguarded_reference_to_plain_input_is_not_linted(self, load_empty_library: Callable[[], None]):
        """The lint only applies to declared-optional inputs."""
        load_empty_library()
        pipe_llm = _make_pipe_llm(prompt="Write a report.\n$contract\n@?assessment")
        assert pipe_llm.code == "guard_lint_llm"

    # ---- PipeCondition expressions ----

    def test_unguarded_optional_in_condition_expression_is_rejected(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeCondition].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="guard_lint_condition",
                blueprint=PipeConditionBlueprint(
                    description="Condition on a maybe-absent slot, unguarded",
                    inputs={"maybe_var": "Text?"},
                    output="Text?",
                    expression="maybe_var",
                    outcomes={"yes": "continue"},
                    default_outcome="continue",
                ),
            )
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED

    def test_presence_branching_idiom_is_accepted(self, load_empty_library: Callable[[], None]):
        """The design §15 idiom: branch on presence with an `is defined` inline conditional."""
        load_empty_library()
        condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="guard_lint_condition_ok",
            blueprint=PipeConditionBlueprint(
                description="Condition branching on presence",
                inputs={"maybe_var": "Text?"},
                output="Text?",
                expression_template="{{ 'present' if maybe_var is defined else 'absent' }}",
                outcomes={"present": "continue", "absent": "continue"},
                default_outcome="continue",
            ),
        )
        assert condition.code == "guard_lint_condition_ok"

    # ---- PipeCompose templates ----

    def test_unguarded_optional_in_compose_template_is_rejected(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeCompose].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="guard_lint_compose",
                blueprint=PipeComposeBlueprint(
                    description="Compose over a maybe-absent slot, unguarded",
                    inputs={"maybe_note": "Text?"},
                    output="Text",
                    template="note: {{ maybe_note }}",
                ),
            )
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED

    # ---- PipeSearch / PipeImgGen templates ----

    def test_unguarded_optional_in_search_prompt_is_rejected(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeSearch].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="guard_lint_search",
                blueprint=PipeSearchBlueprint(
                    description="Search over a maybe-absent slot, unguarded",
                    inputs={"maybe_topic": "Text?"},
                    output="SearchResult[]",
                    prompt="latest news about {{ maybe_topic }}",
                ),
            )
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED

    def test_unguarded_optional_in_img_gen_prompt_is_rejected(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        with pytest.raises(ValidationError) as exc_info:
            PipeFactory[PipeImgGen].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="guard_lint_img_gen",
                blueprint=PipeImgGenBlueprint(
                    description="Image prompt over a maybe-absent slot, unguarded",
                    inputs={"maybe_style": "Text?"},
                    output="Image",
                    prompt="a landscape in the style of {{ maybe_style }}",
                ),
            )
        wrapped = extract_wrapped_pipe_validation_error(exc_info.value.errors()[0])
        assert wrapped is not None
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED

    # ---- Unparseable templates stay the parsing gates' concern ----

    def test_broken_expression_does_not_leak_internal_error(self, load_empty_library: Callable[[], None]):
        """A syntactically broken expression on a pipe with optional inputs must not surface the
        internal Jinja2DetectVariablesError through the guard-lint at construction time — syntax
        errors belong to the template-parsing gates and their typed channels.
        """
        load_empty_library()
        try:
            PipeFactory[PipeCondition].make_from_blueprint(
                domain_code=_DOMAIN_CODE,
                pipe_code="guard_lint_broken_expression",
                blueprint=PipeConditionBlueprint(
                    description="Condition with a broken expression over an optional input",
                    inputs={"maybe_var": "Text?"},
                    output="Text?",
                    expression_template="{{ maybe_var.",
                    outcomes={"yes": "continue"},
                    default_outcome="continue",
                ),
            )
        except ValidationError:
            # A wrapped pydantic error from a parsing gate is fine — a raw
            # Jinja2DetectVariablesError escaping construction is what this test forbids.
            pass

    def test_guarded_compose_template_is_accepted(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        compose = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="guard_lint_compose_ok",
            blueprint=PipeComposeBlueprint(
                description="Compose handling both arms",
                inputs={"maybe_note": "Text?"},
                output="Text",
                template="{% if maybe_note %}note: {{ maybe_note }}{% else %}no note{% endif %}",
            ),
        )
        assert compose.code == "guard_lint_compose_ok"

    def test_escaped_dollar_literal_in_compose_is_not_a_false_positive(self, load_empty_library: Callable[[], None]):
        """Regression: `$$maybe_note` is an escaped literal `$maybe_note`, not a reference.

        PipeCompose must store its template in authored form so the guard-lint rewrites sigils
        exactly once. When PipeCompose stored the already-preprocessed template instead, the
        lint's own `rewrite_template_sigils` ran a second time and resurrected the escaped
        literal (`$$maybe_note` → `$maybe_note` → `{{ maybe_note|format() }}`), wrongly raising
        OPTIONAL_INPUT_UNGUARDED on a pipe that never references the optional input.
        """
        load_empty_library()
        compose = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="guard_lint_compose_escaped",
            blueprint=PipeComposeBlueprint(
                description="Compose whose template escapes a literal `$` before an optional input's name",
                inputs={"maybe_note": "Text?"},
                output="Text",
                template="The literal token is $$maybe_note here.",
            ),
        )
        assert compose.code == "guard_lint_compose_escaped"
        # The stored template stays authored (escaped), so a single downstream rewrite keeps it literal.
        assert compose.template == "The literal token is $$maybe_note here."
