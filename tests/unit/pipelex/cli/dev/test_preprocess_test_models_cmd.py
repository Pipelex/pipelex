"""Unit tests for the `pipelex-dev preprocess-test-models` command."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cli.dev_cli.commands.preprocess_test_models_cmd import (
    _fetch_gateway_models,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.system.pipelex_service.exceptions import RemoteConfigUnavailableError, RemoteConfigValidationError
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher


class TestPreprocessTestModelsCmd:
    @pytest.mark.parametrize(
        "gateway_error",
        [
            RemoteConfigUnavailableError("gateway offline"),
            RemoteConfigValidationError("gateway schema break"),
        ],
    )
    def test_fetch_gateway_models_propagates_fresh_refusal(self, mocker: MockerFixture, gateway_error: Exception) -> None:
        """``require_fresh=True`` must refuse to proceed when the Gateway config is unavailable
        or stale. The error propagates instead of being swallowed into empty model lists, so
        offline fixture generation cannot silently drop every ``pipelex_gateway`` model.
        """
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", side_effect=gateway_error)

        with pytest.raises((RemoteConfigUnavailableError, RemoteConfigValidationError)) as exc_info:
            _fetch_gateway_models()

        assert exc_info.value is gateway_error, "the fresh-config refusal must propagate verbatim, not be converted into empty model lists"
