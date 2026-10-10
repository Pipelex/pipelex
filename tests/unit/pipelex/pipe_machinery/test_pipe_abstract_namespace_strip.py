import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.tools.log.log_fields import USER_ACTION_FIELD


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

    def test_the_strip_warning_names_the_code_as_it_was_written(self, mocker: MockerFixture) -> None:
        """The warning's message is the same for every code, and its field is the dotted code the author wrote, the one to fix."""
        warning_spy = mocker.spy(log, "warning")

        PipeAbstract.validate_pipe_code_syntax("domain.my_pipe")

        warning_spy.assert_called_once_with(
            "A namespace prefix was stripped from a pipe code",
            fields={"pipe_code": "my_pipe", "pipe_ref": "domain.my_pipe", USER_ACTION_FIELD: "Write the pipe code bare"},
        )

    def test_validate_pipe_code_syntax_raises_for_invalid_after_strip(self) -> None:
        """A dotted code whose bare part is not snake_case should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid pipe code syntax"):
            PipeAbstract.validate_pipe_code_syntax("domain.NotSnakeCase")
