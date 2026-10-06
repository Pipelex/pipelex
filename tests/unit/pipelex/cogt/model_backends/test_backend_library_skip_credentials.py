"""A keyless load keeps every enabled backend and resolves none of its credentials.

`CredentialResolution.SKIP` is the keyless boot (validate, show, dry runs): it resolves nothing and
asks the secrets provider nothing, but keeps every enabled backend with its models and constraints, so
a validation gives the same verdict on a machine with no key as on one with all of them. What it
records instead is what it left unresolved, which is what refuses a call to that backend later.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.providers.openai.vertexai_factory import VertexAIFactory
from tests.helpers.backend_library_loading import load_library, required_backend
from tests.helpers.recording_secrets_provider import RecordingSecretsProvider
from tests.unit.pipelex.cogt.model_backends.test_data import ABSENT_VAR, BackendLibraryTomls


class TestSkipKeepsEveryBackendAndResolvesNothing:
    @pytest.mark.parametrize("secrets_provider", [RecordingSecretsProvider.make_empty(), RecordingSecretsProvider.make_credentialed()])
    def test_it_keeps_the_backend_its_models_and_its_constraints_and_asks_nothing(
        self, tmp_path: Path, secrets_provider: RecordingSecretsProvider
    ) -> None:
        """Whether the provider holds the key or not, the keyless load is the same and never consults it."""
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_EVERY_CREDENTIAL_SHAPE,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
            secrets_provider=secrets_provider,
        )

        backend = required_backend(library)
        assert list(backend.model_specs) == ["acme-one"]
        assert backend.listed_constraints == [ListedConstraint.TEMPERATURE_UNSUPPORTED]
        assert backend.valued_constraints == {ValuedConstraint.FIXED_TEMPERATURE: 1}
        assert secrets_provider.looked_up == []

    def test_it_leaves_every_templated_field_unset_and_names_its_variables(self, tmp_path: Path) -> None:
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_EVERY_CREDENTIAL_SHAPE,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        backend = required_backend(library)
        assert backend.endpoint is None
        assert backend.api_key is None
        assert "region" not in backend.extra_config
        assert backend.extra_config == {"debug": True}
        assert backend.unresolved_credentials == {
            "endpoint": ["ACME_ENDPOINT"],
            "api_key": ["ACME_API_KEY"],
            "region": ["ACME_REGION"],
        }
        assert backend.unresolved_credential_vars == ["ACME_API_KEY", "ACME_ENDPOINT", "ACME_REGION"]

    def test_it_keeps_a_literal_endpoint(self, tmp_path: Path) -> None:
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        backend = required_backend(library)
        assert backend.endpoint == "https://api.acme.example/v1"
        assert backend.unresolved_credentials == {"api_key": ["ACME_API_KEY"]}

    def test_a_backend_that_references_no_variable_has_nothing_unresolved(self, tmp_path: Path) -> None:
        """Ollama's shape: nothing was skipped, so nothing will refuse a call to it."""
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_NO_CREDENTIAL,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        backend = required_backend(library)
        assert backend.endpoint == "http://localhost:11434/v1"
        assert backend.unresolved_credentials == {}

    @pytest.mark.parametrize(
        ("model_specs_toml", "expected_vars"),
        [
            (BackendLibraryTomls.MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL, [ABSENT_VAR]),
            (BackendLibraryTomls.MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN, [f"{ABSENT_VAR}_A", f"{ABSENT_VAR}_B"]),
        ],
    )
    def test_a_templated_model_spec_keeps_its_text_and_names_its_variables(
        self, tmp_path: Path, model_specs_toml: str, expected_vars: list[str]
    ) -> None:
        """The spec must still validate, so its text is kept; the variables still refuse a call to the backend."""
        library = load_library(
            tmp_path, backends_toml=BackendLibraryTomls.BACKENDS_TOML, model_specs_toml=model_specs_toml, credentials=CredentialResolution.SKIP
        )

        backend = required_backend(library)
        assert backend.model_specs["acme-one"].model_id.startswith("${")
        assert backend.unresolved_credentials == {"model_specs": expected_vars}

    def test_a_missing_backend_credential_keeps_the_backend(self, tmp_path: Path) -> None:
        """The keyless boot used to drop this backend, and every model it served with it."""
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_MISSING_CREDENTIAL,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        assert required_backend(library).unresolved_credential_vars == [ABSENT_VAR]

    def test_an_enabled_vertexai_backend_mints_no_token_and_touches_no_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Minting the access token is the credential resolution this mode does not do, network call included."""
        make_endpoint_and_api_key = mocker.spy(VertexAIFactory, "make_endpoint_and_api_key")

        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.VERTEXAI_BACKENDS_TOML,
            model_specs_toml=BackendLibraryTomls.VERTEXAI_MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
            backend_name="vertexai",
        )

        backend = required_backend(library, "vertexai")
        make_endpoint_and_api_key.assert_not_called()
        assert backend.endpoint is None
        assert backend.api_key is None
        assert list(backend.model_specs) == ["gemini-one"]
        # No variable names this token: it is minted from the service-account file, so the field alone is recorded.
        assert backend.unresolved_credentials == {"endpoint": [], "api_key": []}
