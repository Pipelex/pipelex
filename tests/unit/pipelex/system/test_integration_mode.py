import pytest

from pipelex.system.runtime import IntegrationMode


class TestIntegrationMode:
    def test_only_the_cli_is_the_pipelex_command_line(self):
        """The CLI integration is the one whose user can act on command-line advice such as `pipelex login`."""
        assert IntegrationMode.CLI.is_pipelex_command_line is True

    @pytest.mark.parametrize("integration_mode", [mode for mode in IntegrationMode if mode is not IntegrationMode.CLI])
    def test_every_other_integration_is_not_the_pipelex_command_line(self, integration_mode: IntegrationMode):
        """A server, a test run or an embedding program is never offered command-line advice."""
        assert integration_mode.is_pipelex_command_line is False
