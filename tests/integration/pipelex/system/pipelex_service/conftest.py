import os

import pytest
from pytest_mock import MockerFixture

from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.system.telemetry.otel_constants import OTelConstants


@pytest.fixture
def gateway_telemetry_reachable(mocker: MockerFixture) -> None:
    """Clear what would stop a boot from building the Gateway telemetry stream, and send nothing.

    A placeholder gateway key and no `DO_NOT_TRACK`, so a boot that turns the stream on builds the real
    manager instead of refusing, which makes a test's assertion on the stream the thing that fails. PostHog
    is a mock, so that manager reaches no network, and the PostHog module globals it sets are restored
    after the test.
    """
    mocker.patch.dict(os.environ, {PipelexDetails.PIPELEX_GATEWAY_API_KEY_VAR: "placeholder-gateway-key"})
    os.environ.pop(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY, None)
    mocker.patch("pipelex.system.telemetry.telemetry_manager.Posthog")
    mocker.patch("posthog.default_client", None)
    mocker.patch("posthog.privacy_mode", False)
