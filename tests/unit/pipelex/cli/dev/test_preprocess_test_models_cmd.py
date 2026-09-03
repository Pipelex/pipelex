"""Unit tests for the `pipelex-dev preprocess-test-models` command."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cli.dev_cli.commands import preprocess_test_models_cmd
from pipelex.cli.dev_cli.commands.preprocess_test_models_cmd import (
    _fetch_managed_gateway_models,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.system.pipelex_service.exceptions import RemoteConfigUnavailableError, RemoteConfigValidationError
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher


class TestPreprocessTestModelsCmd:
    @pytest.mark.parametrize(
        "gateway_error",
        [
            RemoteConfigUnavailableError("service offline"),
            RemoteConfigValidationError("service schema break"),
        ],
    )
    def test_fetch_managed_gateway_models_propagates_fresh_refusal(self, mocker: MockerFixture, gateway_error: Exception) -> None:
        """``require_fresh=True`` must refuse to proceed when the remote config is unavailable
        or stale. The error propagates instead of being swallowed into empty model lists, so
        offline fixture generation cannot silently drop every managed gateway model.
        """
        mocker.patch.object(
            preprocess_test_models_cmd,
            "enabled_managed_gateway_sections",
            return_value={"pipelex_gateway": "backend_model_specs"},
        )
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", side_effect=gateway_error)

        with pytest.raises((RemoteConfigUnavailableError, RemoteConfigValidationError)) as exc_info:
            _fetch_managed_gateway_models()

        assert exc_info.value is gateway_error, "the fresh-config refusal must propagate verbatim, not be converted into empty model lists"

    def test_fetch_managed_gateway_models_skips_the_fetch_when_none_is_enabled(self, mocker: MockerFixture) -> None:
        """No managed gateway backend means no reason to reach the network at all."""
        mocker.patch.object(preprocess_test_models_cmd, "enabled_managed_gateway_sections", return_value={})
        fetch = mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config")

        assert _fetch_managed_gateway_models() == {}
        fetch.assert_not_called()

    def test_fetch_managed_gateway_models_reads_each_backend_its_own_section(self, mocker: MockerFixture) -> None:
        """The point of the generalization: two managed backends, two sections, no hardcoded name.

        A backend whose declared section the artifact does not carry contributes nothing rather
        than failing the run — the same posture the runtime takes.
        """
        mocker.patch.object(
            preprocess_test_models_cmd,
            "enabled_managed_gateway_sections",
            return_value={
                "pipelex_gateway": "backend_model_specs",
                "pipelex_manifold": "manifold_model_specs",
                "absent_gateway": "no_such_section",
            },
        )
        sections = {
            "backend_model_specs": {"defaults": {"model_type": "llm"}, "on-the-cloud": {}},
            "manifold_model_specs": {"defaults": {"model_type": "llm"}, "in-our-vpc": {"model_type": "search"}},
        }
        config = mocker.Mock()
        config.get_model_specs_section.side_effect = sections.get
        mocker.patch.object(RemoteConfigFetcher, "fetch_remote_config", return_value=mocker.Mock(config=config))

        result = _fetch_managed_gateway_models()

        assert set(result) == {"pipelex_gateway", "pipelex_manifold"}
        assert result["pipelex_gateway"]["llm"] == ["on-the-cloud"]
        assert result["pipelex_manifold"]["llm"] == []
        assert result["pipelex_manifold"]["search"] == ["in-our-vpc"]
