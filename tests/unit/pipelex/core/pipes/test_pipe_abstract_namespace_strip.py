import pytest

from pipelex.core.pipes.pipe_abstract import PipeAbstract


class TestPipeAbstractNamespaceStrip:
    """Tests for PipeAbstract.validate_pipe_code_syntax namespace prefix stripping."""

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("domain.my_pipe", "my_pipe"),
            ("a.b.my_pipe", "my_pipe"),
            ("my_pipe", "my_pipe"),
        ],
    )
    def test_validate_pipe_code_syntax_strips_namespace(self, code: str, expected: str) -> None:
        """Dotted pipe codes should be stripped to bare snake_case; bare codes pass through."""
        result = PipeAbstract.validate_pipe_code_syntax(code)
        assert result == expected

    def test_validate_pipe_code_syntax_raises_for_invalid_after_strip(self) -> None:
        """A dotted code whose bare part is not snake_case should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid pipe code syntax"):
            PipeAbstract.validate_pipe_code_syntax("domain.NotSnakeCase")
