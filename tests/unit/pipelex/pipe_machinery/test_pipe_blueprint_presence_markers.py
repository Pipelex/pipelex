import pytest
from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.mthds_parsing.handle_pipe_errors import extract_wrapped_pipe_validation_error
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


class ConcretePipeBlueprint(PipeBlueprint):
    pass


def _make_blueprint(*, inputs: dict[str, str] | None = None, output: str = "Text") -> ConcretePipeBlueprint:
    return ConcretePipeBlueprint(
        type="PipeLLM",
        pipe_category="PipeOperator",
        description="presence marker test pipe",
        inputs=inputs,
        output=output,
    )


def _extract_marker_error(exc: ValidationError) -> PipeValidationError:
    """The blueprint must raise a typed PipeValidationError that survives pydantic wrapping."""
    for error_details in exc.errors():
        wrapped = extract_wrapped_pipe_validation_error(error_details)
        if wrapped is not None:
            return wrapped
    msg = f"No wrapped PipeValidationError found in: {exc}"
    raise AssertionError(msg)


class TestPipeBlueprintPresenceMarkers:
    """Blueprint-parse-time grammar rules for `?` and `!` (D1, D4)."""

    # ---- accepted forms ----

    @pytest.mark.parametrize("input_spec", ["Text?", "Text!", "domain.Concept?", "domain.Concept!"])
    def test_singular_input_markers_accepted(self, input_spec: str):
        blueprint = _make_blueprint(inputs={"the_var": input_spec})
        assert blueprint.inputs == {"the_var": input_spec}

    @pytest.mark.parametrize("input_spec", ["Text[1]?", "Text[1]!", "domain.Concept[1]?"])
    def test_marker_on_count_of_one_input_accepted(self, input_spec: str):
        """`[1]` is the single form with its count written out, so it takes a marker like a bare ref."""
        blueprint = _make_blueprint(inputs={"the_var": input_spec})
        assert blueprint.inputs == {"the_var": input_spec}

    @pytest.mark.parametrize("output_spec", ["Text?", "domain.Concept?"])
    def test_optional_output_accepted(self, output_spec: str):
        blueprint = _make_blueprint(output=output_spec)
        assert blueprint.output == output_spec

    # ---- rejected forms: typed OPTIONAL_MARKER_INVALID ----

    @pytest.mark.parametrize("input_spec", ["Text[]?", "Text[3]?", "Text[]!", "Text[3]!"])
    def test_marker_on_plural_input_rejected(self, input_spec: str):
        with pytest.raises(ValidationError) as exc_info:
            _make_blueprint(inputs={"the_var": input_spec})
        wrapped = _extract_marker_error(exc_info.value)
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_MARKER_INVALID
        assert wrapped.variable_names == ["the_var"]

    @pytest.mark.parametrize("output_spec", ["Text[]?", "Text[3]?"])
    def test_optional_marker_on_plural_output_rejected(self, output_spec: str):
        with pytest.raises(ValidationError) as exc_info:
            _make_blueprint(output=output_spec)
        wrapped = _extract_marker_error(exc_info.value)
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_MARKER_INVALID

    @pytest.mark.parametrize("output_spec", ["Text!", "domain.Concept!", "Text[]!"])
    def test_force_marker_on_output_rejected(self, output_spec: str):
        """`!` is a use-site assertion: it is meaningless on outputs."""
        with pytest.raises(ValidationError) as exc_info:
            _make_blueprint(output=output_spec)
        wrapped = _extract_marker_error(exc_info.value)
        assert wrapped.error_type == PipeValidationErrorType.OPTIONAL_MARKER_INVALID

    # ---- rejected forms: plain syntax errors ----

    @pytest.mark.parametrize("input_spec", ["Text[0]", "Text[0]?", "Text[0]!", "domain.Concept[0]"])
    def test_zero_count_input_rejected(self, input_spec: str):
        with pytest.raises(ValidationError, match="at least 1"):
            _make_blueprint(inputs={"the_var": input_spec})

    @pytest.mark.parametrize("input_spec", ["Text??", "Text?[]", "?Text"])
    def test_malformed_marker_input_syntax_rejected(self, input_spec: str):
        with pytest.raises(ValidationError, match="Invalid input syntax"):
            _make_blueprint(inputs={"the_var": input_spec})

    @pytest.mark.parametrize("output_spec", ["Text??", "Text?[]", "!Text"])
    def test_malformed_marker_output_syntax_rejected(self, output_spec: str):
        with pytest.raises(ValidationError, match="Invalid concept specification syntax"):
            _make_blueprint(output=output_spec)
