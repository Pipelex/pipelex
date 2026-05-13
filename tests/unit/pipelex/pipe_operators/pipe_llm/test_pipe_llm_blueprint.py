import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


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

    def test_validate_inputs_ignores_special_variables(self):
        """Test that special variables like preliminary_text are ignored."""
        blueprint = PipeLLMBlueprint(
            description="lorem ipsum",
            inputs=None,
            output="native.Text",
            prompt="Use $preliminary_text and $place_holder",
        )
        # Should not raise error even though these special variables are not in inputs
        assert blueprint.inputs is None

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
