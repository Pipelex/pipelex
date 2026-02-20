import pytest

from pipelex.builder.pipe.pipe_spec import PipeSpec


class TestPipeSpecCodeValidation:
    """Tests for PipeSpec.validate_pipe_code_syntax namespace prefix stripping and ASCII normalization."""

    @pytest.mark.parametrize(
        ("pipe_code", "expected"),
        [
            ("domain.my_pipe", "my_pipe"),
            ("a.b.my_pipe", "my_pipe"),
            ("my_pipe", "my_pipe"),
            ("d\u00f6main.my_pipe", "my_pipe"),
        ],
        ids=["single_dot", "multi_dot", "passthrough", "unicode_with_dot"],
    )
    def test_validate_pipe_code_syntax_strips_namespace(self, pipe_code: str, expected: str) -> None:
        """Dotted pipe codes should strip namespace first, then normalize ASCII; bare codes pass through."""
        result = PipeSpec.validate_pipe_code_syntax(pipe_code)
        assert result == expected

    def test_validate_pipe_code_syntax_raises_for_invalid_after_strip(self) -> None:
        """A dotted code whose bare part is not snake_case should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid pipe code syntax"):
            PipeSpec.validate_pipe_code_syntax("domain.NotSnakeCase")
