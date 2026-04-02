"""Regression test: gateway terms check must be gated on needs_inference, not needs_model_specs.

Commands like ``pipelex-agent validate bundle`` use ``needs_inference=False, needs_model_specs=True``
to load model specs for validation without actually calling inference APIs. These commands must
NOT require gateway terms acceptance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.pipelex import Pipelex
from pipelex.system.pipelex_service.exceptions import GatewayTermsNotAcceptedError
from pipelex.system.runtime import IntegrationMode

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PIPELEX_MODULE = "pipelex.pipelex"


class TestGatewayTermsCheck:
    """Verify that the terms check in Pipelex.setup() respects needs_inference."""

    @pytest.fixture
    def _gateway_enabled_terms_not_accepted(self, mocker: MockerFixture) -> None:
        """Configure mocks: gateway is enabled but terms have NOT been accepted."""
        mocker.patch(f"{PIPELEX_MODULE}.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch(f"{PIPELEX_MODULE}.load_pipelex_service_config_if_exists", return_value=None)

    @pytest.mark.usefixtures("_gateway_enabled_terms_not_accepted")
    def test_needs_inference_true_raises_when_terms_not_accepted(
        self,
    ) -> None:
        """With needs_inference=True and terms not accepted, setup must raise GatewayTermsNotAcceptedError."""
        pipelex_instance = Pipelex.__new__(Pipelex)

        with pytest.raises(GatewayTermsNotAcceptedError):
            pipelex_instance.setup(
                integration_mode=IntegrationMode.CLI,
                needs_inference=True,
                needs_model_specs=True,
            )

    @pytest.mark.usefixtures("_gateway_enabled_terms_not_accepted")
    def test_needs_inference_false_does_not_raise_when_terms_not_accepted(
        self,
        mocker: MockerFixture,
    ) -> None:
        """With needs_inference=False and needs_model_specs=True, setup must NOT raise GatewayTermsNotAcceptedError.

        It may fail later (e.g., during remote config fetch), but the terms check itself must be skipped.
        """
        # Mock the remote config fetch so we don't hit the network
        mock_remote_config = mocker.MagicMock()
        mock_remote_config.backend_model_specs = {}
        mocker.patch(f"{PIPELEX_MODULE}.RemoteConfigFetcher.fetch_remote_config", return_value=mock_remote_config)

        pipelex_instance = Pipelex.__new__(Pipelex)

        # setup() will fail somewhere after the gateway check (telemetry, models, etc.)
        # but it must NOT fail with GatewayTermsNotAcceptedError
        try:
            pipelex_instance.setup(
                integration_mode=IntegrationMode.CLI,
                needs_inference=False,
                needs_model_specs=True,
            )
        except GatewayTermsNotAcceptedError:
            pytest.fail("setup() raised GatewayTermsNotAcceptedError even though needs_inference=False")
        except Exception:  # noqa: S110
            # Expected: setup() will fail later in the init chain (telemetry, models, etc.)
            # We only care that it did NOT fail with GatewayTermsNotAcceptedError
            pass
