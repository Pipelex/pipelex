import pytest
from pydantic import ValidationError

from pipelex.builder.pipe.pipe_spec import PipeSpec


def _make_spec(*, inputs: dict[str, str] | None = None, output: str = "Text") -> PipeSpec:
    return PipeSpec(
        pipe_code="marker_test_pipe",
        type="PipeLLM",
        pipe_category="PipeOperator",
        description="presence marker test pipe",
        inputs=inputs or {},
        output=output,
    )


class TestPipeSpecPresenceMarkers:
    """Builder specs mirror the blueprint grammar rules for `?` and `!` (D5)."""

    @pytest.mark.parametrize("input_spec", ["Text?", "Text!", "domain.Concept?", "domain.Concept!"])
    def test_singular_input_markers_accepted(self, input_spec: str):
        spec = _make_spec(inputs={"the_var": input_spec})
        assert spec.inputs == {"the_var": input_spec}

    @pytest.mark.parametrize("input_spec", ["Text[1]?", "Text[1]!", "domain.Concept[1]?"])
    def test_marker_on_count_of_one_input_accepted(self, input_spec: str):
        """`[1]` is the single form with its count written out, so it takes a marker like a bare ref."""
        spec = _make_spec(inputs={"the_var": input_spec})
        assert spec.inputs == {"the_var": input_spec}

    @pytest.mark.parametrize("output_spec", ["Text?", "domain.Concept?"])
    def test_optional_output_accepted(self, output_spec: str):
        spec = _make_spec(output=output_spec)
        assert spec.output == output_spec

    def test_to_blueprint_passes_markers_through(self):
        spec = _make_spec(inputs={"maybe_var": "Text?", "must_var": "Text!"}, output="Text?")
        blueprint = spec.to_blueprint()
        assert blueprint.inputs == {"maybe_var": "Text?", "must_var": "Text!"}
        assert blueprint.output == "Text?"

    @pytest.mark.parametrize("input_spec", ["Text[]?", "Text[3]?", "Text[]!"])
    def test_marker_on_plural_input_rejected(self, input_spec: str):
        with pytest.raises(ValidationError, match="cannot be combined with multiplicity"):
            _make_spec(inputs={"the_var": input_spec})

    @pytest.mark.parametrize("output_spec", ["Text[]?", "Text[3]?"])
    def test_optional_marker_on_plural_output_rejected(self, output_spec: str):
        with pytest.raises(ValidationError, match="cannot be combined with multiplicity"):
            _make_spec(output=output_spec)

    @pytest.mark.parametrize("output_spec", ["Text!", "domain.Concept!"])
    def test_force_marker_on_output_rejected(self, output_spec: str):
        with pytest.raises(ValidationError, match="not allowed on outputs"):
            _make_spec(output=output_spec)

    @pytest.mark.parametrize("input_spec", ["Text[0]", "Text[0]?", "Text[0]!", "domain.Concept[0]"])
    def test_zero_count_input_rejected(self, input_spec: str):
        with pytest.raises(ValidationError, match="at least 1"):
            _make_spec(inputs={"the_var": input_spec})

    @pytest.mark.parametrize("input_spec", ["Text??", "Text?[]"])
    def test_malformed_marker_input_syntax_rejected(self, input_spec: str):
        with pytest.raises(ValidationError, match="Invalid input syntax"):
            _make_spec(inputs={"the_var": input_spec})
