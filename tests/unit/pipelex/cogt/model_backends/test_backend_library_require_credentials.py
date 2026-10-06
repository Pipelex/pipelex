"""A load that resolves credentials resolves every one of them, or names the variable it could not.

`CredentialResolution.REQUIRE` is the boot that needs inference: every placeholder is resolved, and a
missing credential is an error naming the variable, which the boot turns into "set this key".
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from tests.helpers.backend_library_loading import load_library, required_backend
from tests.helpers.recording_secrets_provider import RecordingSecretsProvider
from tests.unit.pipelex.cogt.model_backends.test_data import ABSENT_VAR, BackendLibraryTomls


class TestRequireResolvesEveryCredential:
    @pytest.mark.parametrize(
        ("backends_toml", "model_specs_toml"),
        [
            (BackendLibraryTomls.BACKENDS_TOML_WITH_MISSING_CREDENTIAL, BackendLibraryTomls.MODEL_SPECS_TOML),
            (BackendLibraryTomls.BACKENDS_TOML, BackendLibraryTomls.MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL),
        ],
    )
    def test_a_missing_credential_raises_a_credentials_error(
        self,
        tmp_path: Path,
        backends_toml: str,
        model_specs_toml: str,
    ) -> None:
        """Both placements name the variable — that is what the boot turns into 'set this key'."""
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            load_library(tmp_path, backends_toml=backends_toml, model_specs_toml=model_specs_toml, credentials=CredentialResolution.REQUIRE)

        assert exc_info.value.key_name == ABSENT_VAR
        assert exc_info.value.backend_name == "acme"

    def test_an_unresolvable_model_spec_fallback_pattern_raises_a_credentials_error(self, tmp_path: Path) -> None:
        """No single variable name is right when several were tried, but the error still names the backend."""
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN,
                credentials=CredentialResolution.REQUIRE,
            )

        assert exc_info.value.credentials_error_type is InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN
        assert exc_info.value.backend_name == "acme"

    def test_an_empty_provider_refuses_the_backend(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
                credentials=CredentialResolution.REQUIRE,
                secrets_provider=RecordingSecretsProvider.make_empty(),
            )

        assert exc_info.value.key_name == "ACME_API_KEY"

    def test_a_credentialed_provider_gives_the_substituted_key_and_leaves_nothing_unresolved(self, tmp_path: Path) -> None:
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.REQUIRE,
            secrets_provider=RecordingSecretsProvider.make_credentialed(),
        )

        backend = required_backend(library)
        assert backend.api_key == "fake-key"
        assert backend.endpoint == "https://api.acme.example/v1"
        assert backend.unresolved_credentials == {}
        assert backend.unresolved_credential_vars == []
