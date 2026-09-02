"""Unit tests for doctor's check_models — gateway gating and model deck validation paths.

All inference-adjacent collaborators (backend files probe, gateway config fetch,
ModelManager) are mocked at the doctor module namespace: these tests cover the
decision tree, not the model loading itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.commands.doctor_cmd import BackendFileReport, check_models
from pipelex.cogt.exceptions import InferenceBackendLibraryError, ModelDeckValidationError
from pipelex.system.pipelex_service.exceptions import RemoteConfigUnavailableError
from pipelex.system.pipelex_service.types import RemoteConfigSource

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestCheckModels:
    @pytest.fixture
    def healthy_backend_files(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_backend_files",
            return_value=(True, {}, "All backend files are valid"),
        )

    @pytest.fixture
    def gateway_disabled(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cli.commands.doctor_cmd.is_pipelex_gateway_enabled", return_value=False)

    @pytest.fixture
    def models_manager(self, mocker: MockerFixture) -> Any:
        manager_mock = mocker.Mock()
        mocker.patch("pipelex.cli.commands.doctor_cmd.ModelManager", return_value=manager_mock)
        return manager_mock

    def test_backend_files_unhealthy_short_circuits(self, mocker: MockerFixture) -> None:
        """Invalid backend files stop the check before any model loading."""
        bad_report = BackendFileReport(
            backend_name="openai",
            file_path="/cfg/inference/backends/openai.toml",
            is_valid=False,
            error_message="openai: bad spec",
        )
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_backend_files",
            return_value=(False, {"openai": bad_report}, "1 backend file(s) have validation errors"),
        )
        manager_class_mock = mocker.patch("pipelex.cli.commands.doctor_cmd.ModelManager")

        healthy, message, reports = check_models()

        assert healthy is False
        assert message == "Backend configuration error: openai: bad spec"
        assert reports == {"openai": bad_report}
        manager_class_mock.assert_not_called()

    @pytest.mark.usefixtures("healthy_backend_files", "gateway_disabled")
    def test_gateway_disabled_happy_path(self, models_manager: Any) -> None:
        """With the gateway disabled and a valid deck, models are healthy."""
        healthy, message, reports = check_models()

        assert healthy is True
        assert message == "Models are valid"
        assert reports == {}
        models_manager.setup.assert_called_once()
        assert models_manager.setup.call_args.kwargs["gateway_config"] is None
        models_manager.validate_model_deck.assert_called_once()

    @pytest.mark.usefixtures("healthy_backend_files")
    def test_gateway_enabled_missing_service_config(self, mocker: MockerFixture) -> None:
        """Gateway enabled without a service config is unhealthy."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.is_pipelex_gateway_enabled", return_value=True)
        mocker.patch("pipelex.cli.commands.doctor_cmd.load_pipelex_service_config_if_exists", return_value=None)

        healthy, message, _ = check_models()

        assert healthy is False
        assert message == "Pipelex Gateway is enabled but service configuration is missing"

    @pytest.mark.usefixtures("healthy_backend_files")
    def test_gateway_enabled_terms_not_accepted(self, mocker: MockerFixture) -> None:
        """Gateway enabled with unaccepted terms is unhealthy."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.is_pipelex_gateway_enabled", return_value=True)
        service_config = SimpleNamespace(agreement=SimpleNamespace(terms_accepted=False))
        mocker.patch("pipelex.cli.commands.doctor_cmd.load_pipelex_service_config_if_exists", return_value=service_config)

        healthy, message, _ = check_models()

        assert healthy is False
        assert message == "Pipelex Gateway is enabled but terms have not been accepted"

    @pytest.mark.usefixtures("healthy_backend_files")
    def test_gateway_enabled_remote_fetch_failure(self, mocker: MockerFixture) -> None:
        """A failed remote-config fetch is unhealthy with the fetch error in the message."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.is_pipelex_gateway_enabled", return_value=True)
        service_config = SimpleNamespace(agreement=SimpleNamespace(terms_accepted=True))
        mocker.patch("pipelex.cli.commands.doctor_cmd.load_pipelex_service_config_if_exists", return_value=service_config)
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.RemoteConfigFetcher.fetch_remote_config",
            side_effect=RemoteConfigUnavailableError("offline, cold cache"),
        )

        healthy, message, _ = check_models()

        assert healthy is False
        assert message == "Failed to fetch Pipelex Gateway remote configuration: offline, cold cache"

    @pytest.mark.usefixtures("healthy_backend_files")
    def test_gateway_enabled_passes_gateway_config_to_setup(self, mocker: MockerFixture, models_manager: Any) -> None:
        """A successful fetch builds a GatewayConfig and threads it into the model setup."""
        mocker.patch("pipelex.cli.commands.doctor_cmd.is_pipelex_gateway_enabled", return_value=True)
        service_config = SimpleNamespace(agreement=SimpleNamespace(terms_accepted=True))
        mocker.patch("pipelex.cli.commands.doctor_cmd.load_pipelex_service_config_if_exists", return_value=service_config)
        fetch_result = SimpleNamespace(
            config=SimpleNamespace(backend_model_specs={}, aws_region="eu-west-3"),
            source=RemoteConfigSource.FRESH,
        )
        mocker.patch("pipelex.cli.commands.doctor_cmd.RemoteConfigFetcher.fetch_remote_config", return_value=fetch_result)

        healthy, message, _ = check_models()

        assert healthy is True
        assert message == "Models are valid"
        setup_kwargs = models_manager.setup.call_args.kwargs
        assert setup_kwargs["gateway_config"] is not None
        assert setup_kwargs["gateway_config"].aws_region == "eu-west-3"
        assert setup_kwargs["gateway_config_source"] == RemoteConfigSource.FRESH

    @pytest.mark.usefixtures("healthy_backend_files", "gateway_disabled")
    def test_model_deck_validation_error(self, models_manager: Any) -> None:
        """A deck validation failure is reported as a models error."""
        models_manager.validate_model_deck.side_effect = ModelDeckValidationError("preset broken")

        healthy, message, _ = check_models()

        assert healthy is False
        assert message == "Error checking models: preset broken"

    @pytest.mark.usefixtures("gateway_disabled")
    def test_backend_library_error_updates_declared_backend_report(self, mocker: MockerFixture, models_manager: Any) -> None:
        """A library error declaring a known backend flips that backend's report to invalid."""
        openai_report = BackendFileReport(
            backend_name="openai",
            file_path="/cfg/inference/backends/openai.toml",
            is_valid=True,
        )
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_backend_files",
            return_value=(True, {"openai": openai_report}, "All backend files are valid"),
        )
        models_manager.setup.side_effect = InferenceBackendLibraryError("cannot resolve model", backend_name="openai")

        healthy, message, reports = check_models()

        assert healthy is False
        assert message == "Error checking models: cannot resolve model"
        assert reports["openai"].is_valid is False
        assert reports["openai"].error_message == "cannot resolve model"

    @pytest.mark.usefixtures("gateway_disabled")
    def test_backend_library_error_spares_backend_named_only_in_prose(self, mocker: MockerFixture, models_manager: Any) -> None:
        """The loader's unknown-key advice names `x-portkey-provider`, so portkey's name rides in every
        such message. Only the backend the error declares records it — portkey's file is untouched.
        """
        reports_in = {
            "openai": BackendFileReport(backend_name="openai", file_path="/cfg/inference/backends/openai.toml", is_valid=True),
            "portkey": BackendFileReport(backend_name="portkey", file_path="/cfg/inference/backends/portkey.toml", is_valid=True),
        }
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.check_backend_files",
            return_value=(True, reports_in, "All backend files are valid"),
        )
        models_manager.setup.side_effect = InferenceBackendLibraryError(
            "Unknown key 'maxtokens' on model 'gpt-5' for backend 'openai': a per-model key that is not a "
            "model-spec field is sent as a request header and must contain a hyphen (e.g. 'x-portkey-provider')",
            backend_name="openai",
        )

        healthy, _, reports = check_models()

        assert healthy is False
        assert reports["openai"].is_valid is False
        assert reports["portkey"].is_valid is True
        assert reports["portkey"].error_message is None
