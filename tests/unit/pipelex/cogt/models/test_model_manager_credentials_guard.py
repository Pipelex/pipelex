"""The one guard between a keyless boot's backends and a provider client.

A keyless boot keeps every backend but resolves none of their credentials, so a backend it loaded
records what it left unresolved. Every reader of a backend's key, endpoint and extra config reaches
the backend through `ModelManager.get_required_inference_backend`, which refuses such a backend with
a configuration error naming the variables, rather than letting an unset key reach a provider client.
"""

import pytest

from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType, InferenceErrorCategory, ModelManagerError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.models.model_manager import ModelManager


def _manager_with(*backends: InferenceBackend) -> ModelManager:
    manager = ModelManager()
    manager.inference_backend_library.root = {backend.name: backend for backend in backends}
    return manager


class TestModelManagerCredentialsGuard:
    def test_a_backend_left_unresolved_is_refused_with_its_variables(self) -> None:
        manager = _manager_with(
            InferenceBackend(
                name="azure_openai",
                unresolved_credentials={"endpoint": ["AZURE_API_BASE"], "api_key": ["AZURE_API_KEY"]},
            )
        )

        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            manager.get_required_inference_backend("azure_openai")

        error = exc_info.value
        assert error.credentials_error_type is InferenceBackendCredentialsErrorType.NOT_RESOLVED_ON_KEYLESS_BOOT
        assert error.backend_name == "azure_openai"
        assert error.key_name == "AZURE_API_BASE"
        assert "needs_inference=False" in error.message
        assert "endpoint (AZURE_API_BASE), api_key (AZURE_API_KEY)" in error.message

    def test_its_report_is_a_configuration_error_whose_next_step_is_a_boot_with_inference(self) -> None:
        """Setting the variable alone would not help a process that booted without inference."""
        manager = _manager_with(InferenceBackend(name="anthropic", unresolved_credentials={"api_key": ["ANTHROPIC_API_KEY"]}))

        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            manager.get_required_inference_backend("anthropic")

        report = exc_info.value.to_error_report()
        assert report.error_type == "InferenceBackendCredentialsError"
        assert report.error_category is InferenceErrorCategory.CONFIGURATION
        assert report.user_action is not None
        assert report.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        assert "needs_inference=True" in report.user_action.detail

    def test_the_class_keeps_its_own_next_step_elsewhere(self) -> None:
        """The guard's advice is its instance's own: the boot's missing-key error still says to set the variable."""
        error = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="anthropic",
            message="missing",
            key_name="ANTHROPIC_API_KEY",
        )

        assert error.user_action is not None
        assert error.user_action.detail == "Check that the required API key environment variable is set"

    def test_a_field_minted_at_boot_is_named_when_no_variable_is(self) -> None:
        """Vertex AI's token comes from no variable, so the field it fills is what the error names."""
        manager = _manager_with(InferenceBackend(name="vertexai", unresolved_credentials={"endpoint": [], "api_key": []}))

        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            manager.get_required_inference_backend("vertexai")

        assert exc_info.value.key_name == "endpoint"
        assert "Left unresolved: endpoint, api_key." in exc_info.value.message

    def test_a_backend_with_nothing_unresolved_is_handed_out(self) -> None:
        backend = InferenceBackend(name="ollama", endpoint="http://localhost:11434/v1")
        manager = _manager_with(backend)

        assert manager.get_required_inference_backend("ollama") == backend

    def test_an_unknown_backend_is_still_not_found(self) -> None:
        with pytest.raises(ModelManagerError, match="'nowhere' not found"):
            _manager_with().get_required_inference_backend("nowhere")
