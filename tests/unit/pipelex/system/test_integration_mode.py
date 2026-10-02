import pytest

from pipelex.system.runtime import IntegrationMode

IS_TEST_HARNESS_BY_MODE: dict[IntegrationMode, bool] = {
    IntegrationMode.CI: True,
    IntegrationMode.CLI: False,
    IntegrationMode.DOCKER: False,
    IntegrationMode.FASTAPI: False,
    IntegrationMode.MCP: False,
    IntegrationMode.N8N: False,
    IntegrationMode.PYTEST: True,
    IntegrationMode.PYTHON: False,
}


class TestIntegrationModeIsTestHarness:
    @pytest.mark.parametrize(("integration_mode", "expected"), list(IS_TEST_HARNESS_BY_MODE.items()))
    def test_is_test_harness(self, integration_mode: IntegrationMode, expected: bool) -> None:
        """The boot keeps the Gateway telemetry stream off in a harness mode, so each mode's answer is a telemetry decision.

        A deployment mode classified as a harness would silence real usage; a harness mode classified as
        a deployment would send test runs to the production analytics project.
        """
        assert integration_mode.is_test_harness is expected

    def test_the_table_covers_every_mode(self) -> None:
        """A mode added later fails here until someone decides whether it is a test harness."""
        assert set(IS_TEST_HARNESS_BY_MODE) == set(IntegrationMode)
