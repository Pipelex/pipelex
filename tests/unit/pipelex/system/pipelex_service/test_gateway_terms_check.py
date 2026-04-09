"""Regression tests for gateway terms check and first-run inference setup check.

Commands like ``pipelex-agent validate bundle`` use ``needs_inference=False, needs_model_specs=True``
to load model specs for validation without actually calling inference APIs. These commands must
NOT require gateway terms acceptance.

The first-run check (InferenceSetupRequiredError) fires when no service config exists at all,
while the gateway terms check (GatewayTermsNotAcceptedError) fires when the config exists
and inference setup is completed but terms have not been accepted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.pipelex import Pipelex
from pipelex.system.pipelex_service.exceptions import GatewayTermsNotAcceptedError, InferenceSetupRequiredError
from pipelex.system.pipelex_service.pipelex_service_agreement import PipelexServiceAgreement, PipelexServiceOnboarding
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.runtime import IntegrationMode

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PIPELEX_MODULE = "pipelex.pipelex"


class TestGatewayTermsCheck:
    """Verify that the terms check and first-run check in Pipelex.setup() behave correctly."""

    @pytest.fixture
    def _gateway_enabled_no_config(self, mocker: MockerFixture) -> None:
        """Configure mocks: gateway is enabled but no service config exists (first run)."""
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists", return_value=None)

    @pytest.fixture
    def _gateway_enabled_setup_done_terms_not_accepted(self, mocker: MockerFixture) -> None:
        """Configure mocks: gateway enabled, inference setup completed, but terms NOT accepted."""
        config = PipelexServiceConfig(
            agreement=PipelexServiceAgreement(terms_accepted=False),
            onboarding=PipelexServiceOnboarding(inference_setup_completed=True),
        )
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists", return_value=config)

    @pytest.mark.usefixtures("_gateway_enabled_no_config")
    def test_first_run_raises_inference_setup_required(self) -> None:
        """With no service config at all, setup must raise InferenceSetupRequiredError."""
        pipelex_instance = Pipelex.__new__(Pipelex)

        with pytest.raises(InferenceSetupRequiredError):
            pipelex_instance.setup(
                integration_mode=IntegrationMode.CLI,
                needs_inference=True,
                needs_model_specs=True,
            )

    @pytest.mark.usefixtures("_gateway_enabled_setup_done_terms_not_accepted")
    def test_needs_inference_true_raises_when_terms_not_accepted(self) -> None:
        """With inference setup done but terms not accepted, setup must raise GatewayTermsNotAcceptedError."""
        pipelex_instance = Pipelex.__new__(Pipelex)

        with pytest.raises(GatewayTermsNotAcceptedError):
            pipelex_instance.setup(
                integration_mode=IntegrationMode.CLI,
                needs_inference=True,
                needs_model_specs=True,
            )

    @pytest.mark.usefixtures("_gateway_enabled_no_config")
    def test_needs_inference_false_does_not_raise_when_terms_not_accepted(
        self,
        mocker: MockerFixture,
    ) -> None:
        """With needs_inference=False and needs_model_specs=True, setup must NOT raise terms/setup errors.

        It may fail later (e.g., during remote config fetch), but the terms check itself must be skipped.
        """
        # Mock the remote config fetch so we don't hit the network
        mock_remote_config = mocker.MagicMock()
        mock_remote_config.backend_model_specs = {}
        mocker.patch(f"{PIPELEX_MODULE}.RemoteConfigFetcher.fetch_remote_config", return_value=mock_remote_config)

        pipelex_instance = Pipelex.__new__(Pipelex)

        # setup() will fail somewhere after the gateway check (telemetry, models, etc.)
        # but it must NOT fail with GatewayTermsNotAcceptedError or InferenceSetupRequiredError
        try:
            pipelex_instance.setup(
                integration_mode=IntegrationMode.CLI,
                needs_inference=False,
                needs_model_specs=True,
            )
        except (GatewayTermsNotAcceptedError, InferenceSetupRequiredError):
            pytest.fail("setup() raised a terms/setup error even though needs_inference=False")
        except Exception:  # noqa: S110
            # Expected: setup() will fail later in the init chain (telemetry, models, etc.)
            # We only care that it did NOT fail with terms/setup errors
            pass
