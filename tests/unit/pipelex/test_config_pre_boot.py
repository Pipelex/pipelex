from pytest_mock import MockerFixture

from pipelex.config import get_pipe_func_execution_mode, is_pipe_func_sandbox_hosted
from pipelex.hub import PipelexHub, get_optional_config
from pipelex.plugins.pipe_func_executor_registry import DIRECT_PIPE_FUNC_EXECUTION_MODE


class TestConfigPreBoot:
    """The optional config accessors honor their non-raising contract before any hub exists."""

    def test_get_optional_config_returns_none_without_hub(self, mocker: MockerFixture):
        """With no PipelexHub instance at all, the optional getter returns None instead of raising."""
        mocker.patch.object(PipelexHub, "_instance", None)
        assert get_optional_config() is None

    def test_pipe_func_execution_mode_defaults_to_direct_without_hub(self, mocker: MockerFixture):
        """Pre-boot PipeFunc validation must default to direct, not crash on the missing hub."""
        mocker.patch.object(PipelexHub, "_instance", None)
        assert get_pipe_func_execution_mode() == DIRECT_PIPE_FUNC_EXECUTION_MODE
        assert is_pipe_func_sandbox_hosted() is False
