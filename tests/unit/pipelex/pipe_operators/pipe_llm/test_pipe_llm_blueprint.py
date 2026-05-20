import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod


class TestPipeLLMBlueprint:
    def test_validate_inputs_correct_with_prompt_variables(self):
        """Test that prompt variables matching inputs are valid."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs={"input_one": "native.Text", "input_two": "native.Text"},
            output="native.Text",
            prompt="Process $input_one and $input_two",
        )
        assert blueprint.nb_inputs == 2
        assert set(blueprint.input_names) == {"input_one", "input_two"}

    def test_validate_inputs_correct_with_system_prompt_variables(self):
        """Test that system_prompt variables matching inputs are valid."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs={"context": "native.Text"},
            output="native.Text",
            system_prompt="Use this context: $context",
            prompt="Generate a response",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["context"]

    def test_validate_inputs_correct_with_both_prompts(self):
        """Test that variables in both prompt and system_prompt are validated."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs={"context": "native.Text", "query": "native.Text"},
            output="native.Text",
            system_prompt="Context: $context",
            prompt="Answer this query: $query",
        )
        assert blueprint.nb_inputs == 2
        assert set(blueprint.input_names) == {"context", "query"}

    def test_validate_inputs_correct_no_variables(self):
        """Test that prompts without variables work fine."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs=None,
            output="native.Text",
            prompt="Generate a random story",
        )
        assert blueprint.inputs is None

    def test_validate_inputs_correct_with_inline_variables(self):
        """Test that inline variables ($variable) are also validated."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs={"topic": "native.Text", "style": "native.Text"},
            output="native.Text",
            prompt="Write about $topic in $style style",
        )
        assert blueprint.nb_inputs == 2
        assert set(blueprint.input_names) == {"topic", "style"}

    def test_validate_inputs_incorrect_missing_variable(self):
        """Test that missing input variable raises ValueError."""
        with pytest.raises(ValueError, match="Missing input variable") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"input_one": "native.Text", "input_two": "native.Text"},
                output="native.Text",
                prompt="Process $input_one, $input_two, and $input_three",
            )
        error_msg = str(exc_info.value)
        assert "Missing input variable(s):" in error_msg
        assert "input_three" in error_msg
        assert "not declared in inputs" in error_msg

    def test_validate_inputs_incorrect_missing_multiple_variables(self):
        """Test that multiple missing variables are all reported."""
        with pytest.raises(ValueError, match="Missing input variable") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"input_one": "native.Text"},
                output="native.Text",
                prompt="Process $input_one, $input_two, and $input_three",
            )
        error_msg = str(exc_info.value)
        assert "Missing input variable(s):" in error_msg
        assert "input_two" in error_msg
        assert "input_three" in error_msg

    def test_validate_inputs_incorrect_missing_in_system_prompt(self):
        """Test that missing variables in system_prompt are caught."""
        with pytest.raises(ValueError, match="Missing input variable") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"query": "native.Text"},
                output="native.Text",
                system_prompt="Use context: $context",
                prompt="Answer: $query",
            )
        error_msg = str(exc_info.value)
        assert "Missing input variable(s):" in error_msg
        assert "context" in error_msg

    def test_validate_inputs_incorrect_empty_inputs_with_variables(self):
        """Test that variables in prompt require inputs to be declared."""
        with pytest.raises((ValidationError, ValueError)) as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={},
                output="native.Text",
                prompt="Process $data",
            )
        error_msg = str(exc_info.value)
        assert "Missing input variable(s):" in error_msg or "data" in error_msg

    def test_validate_inputs_ignores_internal_variables(self):
        """Test that internal variables (starting with _) are ignored."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs=None,
            output="native.Text",
            prompt="Use internal variable $_internal_var",
        )
        # Should not raise error even though _internal_var is not in inputs
        assert blueprint.inputs is None

    def test_validate_inputs_ignores_place_holder(self):
        """Test that the special variable place_holder is ignored."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs=None,
            output="native.Text",
            prompt="Use $place_holder",
        )
        # Should not raise error even though this special variable is not in inputs
        assert blueprint.inputs is None

    @pytest.mark.parametrize("bad_output", ["Text", "Text[]", "Text[2]", "native.Text"])
    def test_preliminary_text_rejects_text_compatible_output(self, bad_output: str):
        """`structuring_method = preliminary_text` is rejected at blueprint construction when paired with a Text-shaped output."""
        with pytest.raises(ValidationError, match="cannot have output"):
            PipeLLMBlueprint(
                description="Bad",
                output=bad_output,
                prompt="hello",
                structuring_method=StructuringMethod.PRELIMINARY_TEXT,
            )

    def test_preliminary_text_accepts_structured_output(self):
        """`preliminary_text` paired with a non-Text output passes validation."""
        blueprint = PipeLLMBlueprint(
            description="OK",
            output="Foo",
            prompt="hello",
            structuring_method=StructuringMethod.PRELIMINARY_TEXT,
        )
        assert blueprint.structuring_method is StructuringMethod.PRELIMINARY_TEXT
        assert blueprint.output == "Foo"

    def test_direct_method_does_not_trigger_text_check(self):
        """`StructuringMethod.DIRECT` does not trigger the Text-output check, even when output is Text."""
        blueprint = PipeLLMBlueprint(
            description="OK",
            output="Text",
            prompt="hello",
            structuring_method=StructuringMethod.DIRECT,
        )
        assert blueprint.structuring_method is StructuringMethod.DIRECT
        assert blueprint.output == "Text"

    # =========================================================================
    # Strict line-bounded `@` sigil contract — surfaces through pydantic validation
    # =========================================================================

    def test_validate_inputs_raises_for_inline_at_sigil_in_prompt(self):
        """Inline `@var` in the prompt surfaces as a pydantic validation failure
        whose message names the offending span, the line number, and both migration
        hints (`$var` for inline, `@@` for literal).
        """
        with pytest.raises(ValueError, match="@invoice_text") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"invoice_text": "native.Text"},
                output="native.Text",
                prompt="Extract from @invoice_text. Done.",
            )
        error_msg = str(exc_info.value)
        assert "@invoice_text" in error_msg
        assert "$invoice_text" in error_msg
        assert "@@" in error_msg
        assert "line 1" in error_msg

    def test_validate_inputs_raises_for_inline_at_sigil_in_system_prompt(self):
        """Inline `@var` in the system_prompt also surfaces with the strict-rule
        diagnostic — both prompt fields are validated.
        """
        with pytest.raises(ValueError, match="@context") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"context": "native.Text"},
                output="native.Text",
                system_prompt="Hello @context!",
                prompt="Generate a response",
            )
        error_msg = str(exc_info.value)
        assert "@context" in error_msg
        assert "$context" in error_msg
        assert "@@" in error_msg
        assert "line 1" in error_msg

    def test_validate_inputs_raises_with_correct_line_for_multiline_prompt(self):
        """Line number in the diagnostic is 1-based and accurate for multi-line prompts."""
        with pytest.raises(ValueError, match="line 2") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"data": "native.Text"},
                output="native.Text",
                prompt="Header line\nBody with inline @data\nFooter line",
            )
        error_msg = str(exc_info.value)
        assert "line 2" in error_msg
        assert "@data" in error_msg

    # =========================================================================
    # Declared-inputs gating — inline `@<ident>` only raises when `<ident>` is a
    # declared input of the PipeLLM. CSS at-rules and code decorators pass through
    # silently when they don't collide with a declared input.
    # =========================================================================

    def test_inline_css_at_rule_passes_when_keyword_not_declared(self):
        """`<style>@media (...) { ... }</style>` inside a PipeCompose-like prompt loads
        cleanly when `media` is not a declared input. The page input still needs
        a Jinja2 reference for the validator to count it as used, so the prompt also
        renders `$page` inline.
        """
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs={"page": "native.Text"},
            output="native.Text",
            prompt="<style>@media (max-width: 820px) { color: red; }</style>\nFor $page",
        )
        assert blueprint.input_names == ["page"]

    def test_inline_at_raises_when_input_collides_with_at_rule_keyword(self):
        """When a declared input happens to share a name with a CSS at-rule keyword
        (e.g. `media`), the validator treats inline `@media` as a real typo and raises.
        Authors can opt out with `@@media`.
        """
        with pytest.raises(ValueError, match="@media") as exc_info:
            PipeLLMBlueprint(
                description="lorem ipsum",
                inputs={"media": "native.Text"},
                output="native.Text",
                prompt="<style>@media (max-width: 820px) { color: red; }</style>\nFor $media",
            )
        error_msg = str(exc_info.value)
        assert "@media" in error_msg
        assert "$media" in error_msg  # inline migration hint
        assert "@@" in error_msg  # literal-escape hint

    def test_inline_python_decorator_passes_through(self):
        """Inline `@deprecated` (Python decorator shape) in a prompt loads cleanly when
        `deprecated` is not a declared input.
        """
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs={"code": "native.Text"},
            output="native.Text",
            prompt="Review this code with @deprecated def foo(): pass\nCode: $code",
        )
        assert blueprint.input_names == ["code"]
