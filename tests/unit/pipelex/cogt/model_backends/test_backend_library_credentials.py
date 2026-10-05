"""How the library treats credentials in each of its two modes.

`CredentialResolution.REQUIRE` is the boot that needs inference: every placeholder is resolved, and a
missing credential is an error naming the variable. `CredentialResolution.SKIP` is the keyless boot
(validate, show, dry runs): it resolves nothing and asks the secrets provider nothing, but keeps every
enabled backend with its models and constraints, so a validation gives the same verdict on a machine
with no key as on one with all of them. What it records instead is what it left unresolved, which is
what refuses a call to that backend later.

A malformed configuration is fatal in both modes. A config error swallowed by the keyless boot would
delete a whole backend from the library, and every handle it served would then fail much later with
a far more confusing "model not found".
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType, InferenceBackendLibraryError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.providers.openai.vertexai_factory import VertexAIFactory
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from tests.helpers.recording_secrets_provider import RecordingSecretsProvider

ABSENT_VAR = "PIPELEX_TEST_ABSENT_VAR_FOR_CREDENTIALS"

BACKENDS_TOML = """
[acme]
enabled = true
api_key = "sk-not-a-real-key"
"""

BACKENDS_TOML_WITH_MISSING_CREDENTIAL = f"""
[acme]
enabled = true
api_key = "${{{ABSENT_VAR}}}"
"""

MODEL_SPECS_TOML = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
"""

MODEL_SPECS_TOML_WITH_UNKNOWN_DEFAULT = """
[defaults]
model_type = "llm"
sdk = "openai_responses"
a_field_we_removed = "openai"

["acme-one"]
model_id = "acme-one"
"""

MODEL_SPECS_TOML_WITH_UNKNOWN_PER_MODEL_KEY = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
max_tokns = 4096
"""

MODEL_SPECS_TOML_WITH_NEAR_MISS_PER_MODEL_KEY = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
max-tokens = 4096
"""

MODEL_SPECS_TOML_WITH_HEADER_KEY = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
x-portkey-provider = "@openai"
"""

MODEL_SPECS_TOML_WITH_NON_STRING_HEADER_VALUE = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
x-foo = 3
"""

MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_NAME = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
"x-foo bar" = "value"
"""

MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_VALUE = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
x-foo = "trailing "
"""

MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL = f"""
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "${{{ABSENT_VAR}}}"
"""

MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN = f"""
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "${{env:{ABSENT_VAR}_A|env:{ABSENT_VAR}_B}}"
"""


BACKENDS_TOML_WITH_EVERY_CREDENTIAL_SHAPE = """
[acme]
enabled = true
endpoint = "${ACME_ENDPOINT}"
api_key = "${secret:ACME_API_KEY}"
region = "${env:ACME_REGION|secret:ACME_REGION}"
debug = true
listed_constraints = ["temperature_unsupported"]
valued_constraints = { fixed_temperature = 1 }
"""

BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT = """
[acme]
enabled = true
endpoint = "https://api.acme.example/v1"
api_key = "${ACME_API_KEY}"
"""

BACKENDS_TOML_WITH_NO_CREDENTIAL = """
[acme]
enabled = true
endpoint = "http://localhost:11434/v1"
"""

VERTEXAI_BACKENDS_TOML = """
[vertexai]
enabled = true
gcp_project_id = "a-project"
gcp_location = "us-central1"
gcp_credentials_file_path = "/nowhere/service-account.json"
"""

VERTEXAI_MODEL_SPECS_TOML = """
[defaults]
model_type = "llm"
sdk = "openai"

["gemini-one"]
model_id = "google/gemini-one"
"""


def write_config(tmp_path: Path, *, backends_toml: str, model_specs_toml: str | None, backend_name: str = "acme") -> tuple[Path, str]:
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir()
    backends_library_path = tmp_path / "backends.toml"
    backends_library_path.write_text(backends_toml)
    if model_specs_toml is not None:
        (backends_dir / f"{backend_name}.toml").write_text(model_specs_toml)
    return backends_library_path, str(backends_dir)


def load_library(
    tmp_path: Path,
    *,
    backends_toml: str,
    model_specs_toml: str | None,
    credentials: CredentialResolution,
    secrets_provider: SecretsProviderAbstract | None = None,
    backend_name: str = "acme",
) -> InferenceBackendLibrary:
    backends_library_path, backends_dir_path = write_config(
        tmp_path,
        backends_toml=backends_toml,
        model_specs_toml=model_specs_toml,
        backend_name=backend_name,
    )
    library = InferenceBackendLibrary.make_empty()
    library.load(
        secrets_provider=secrets_provider or EnvSecretsProvider(),
        backends_library_paths=[backends_library_path],
        backends_dir_path=backends_dir_path,
        credentials=credentials,
    )
    return library


def required_backend(library: InferenceBackendLibrary, backend_name: str = "acme") -> InferenceBackend:
    backend = library.get_inference_backend(backend_name=backend_name)
    assert backend is not None, f"backend '{backend_name}' is missing from {library.list_backend_names()}"
    return backend


BOTH_MODES = [CredentialResolution.REQUIRE, CredentialResolution.SKIP]


class TestMalformedConfigurationIsFatalInBothModes:
    def test_a_well_formed_backend_loads(self, tmp_path: Path) -> None:
        """The control: without this the failure cases below would prove nothing."""
        library = load_library(tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=MODEL_SPECS_TOML, credentials=CredentialResolution.SKIP)

        assert "acme" in library.root

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_an_unknown_key_in_a_local_backend_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        """A stale local TOML — the shape an upgrade leaves behind, since init never overwrites an existing file."""
        with pytest.raises(InferenceBackendLibraryError, match="a_field_we_removed"):
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_UNKNOWN_DEFAULT,
                credentials=credentials,
            )

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_an_unknown_per_model_key_in_a_local_backend_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        """A per-model typo used to be sent to the provider as a request header, silently, while the
        real setting stayed unset. It is now a boot error that names the key, the model and the file.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_UNKNOWN_PER_MODEL_KEY,
                credentials=credentials,
            )

        message = str(exc_info.value)
        assert "'max_tokns'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "hyphen" in message

    def test_a_hyphenated_spelling_of_a_known_field_is_fatal_and_names_the_field(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendLibraryError, match=r"'max-tokens'.*'max_tokens'"):
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_NEAR_MISS_PER_MODEL_KEY,
                credentials=CredentialResolution.REQUIRE,
            )

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_a_header_shaped_key_with_a_non_string_value_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        """`x-foo = 3` is an unquoted value, not a header to stringify. The message is the rule's, not pydantic's:
        it names the key, the model and the file, and says the value must be a quoted string.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_NON_STRING_HEADER_VALUE,
                credentials=credentials,
            )

        message = str(exc_info.value)
        assert "'x-foo'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "must be a quoted string" in message
        assert "string_type" not in message

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_a_header_shaped_key_the_wire_cannot_carry_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        """A quoted TOML key can hold a character no header field name may carry. Such a key used to load
        fine and raise `LocalProtocolError: Illegal header name` on the first inference call instead.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_NAME,
                credentials=credentials,
            )

        message = str(exc_info.value)
        assert "'x-foo bar'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "' '" in message

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_a_header_value_the_wire_cannot_carry_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        """`x-foo = "trailing "` is valid TOML and the mistake is invisible in the file, which is exactly
        why the error must name it — the HTTP stack otherwise reports it much later, mid-run.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_VALUE,
                credentials=credentials,
            )

        message = str(exc_info.value)
        assert "'x-foo'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "no leading or trailing whitespace" in message

    def test_a_header_shaped_per_model_key_still_becomes_a_request_header(self, tmp_path: Path) -> None:
        """The regression that matters: `x-portkey-provider` in the local portkey.toml keeps working."""
        library = load_library(
            tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=MODEL_SPECS_TOML_WITH_HEADER_KEY, credentials=CredentialResolution.REQUIRE
        )

        model_spec = required_backend(library).model_specs["acme-one"]
        assert model_spec.extra_headers == {"x-portkey-provider": "@openai"}
        assert model_spec.model_id == "acme-one"

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_a_missing_per_backend_toml_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        with pytest.raises(InferenceBackendLibraryError, match=r"acme\.toml"):
            load_library(tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=None, credentials=credentials)


class TestRequireResolvesEveryCredential:
    @pytest.mark.parametrize(
        ("backends_toml", "model_specs_toml"),
        [
            (BACKENDS_TOML_WITH_MISSING_CREDENTIAL, MODEL_SPECS_TOML),
            (BACKENDS_TOML, MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL),
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
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN,
                credentials=CredentialResolution.REQUIRE,
            )

        assert exc_info.value.credentials_error_type is InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN
        assert exc_info.value.backend_name == "acme"

    def test_an_empty_provider_refuses_the_backend(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT,
                model_specs_toml=MODEL_SPECS_TOML,
                credentials=CredentialResolution.REQUIRE,
                secrets_provider=RecordingSecretsProvider.make_empty(),
            )

        assert exc_info.value.key_name == "ACME_API_KEY"

    def test_a_credentialed_provider_gives_the_substituted_key_and_leaves_nothing_unresolved(self, tmp_path: Path) -> None:
        library = load_library(
            tmp_path,
            backends_toml=BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT,
            model_specs_toml=MODEL_SPECS_TOML,
            credentials=CredentialResolution.REQUIRE,
            secrets_provider=RecordingSecretsProvider.make_credentialed(),
        )

        backend = required_backend(library)
        assert backend.api_key == "fake-key"
        assert backend.endpoint == "https://api.acme.example/v1"
        assert backend.unresolved_credentials == {}
        assert backend.unresolved_credential_vars == []


class TestSkipKeepsEveryBackendAndResolvesNothing:
    @pytest.mark.parametrize("secrets_provider", [RecordingSecretsProvider.make_empty(), RecordingSecretsProvider.make_credentialed()])
    def test_it_keeps_the_backend_its_models_and_its_constraints_and_asks_nothing(
        self, tmp_path: Path, secrets_provider: RecordingSecretsProvider
    ) -> None:
        """Whether the provider holds the key or not, the keyless load is the same and never consults it."""
        library = load_library(
            tmp_path,
            backends_toml=BACKENDS_TOML_WITH_EVERY_CREDENTIAL_SHAPE,
            model_specs_toml=MODEL_SPECS_TOML,
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
            backends_toml=BACKENDS_TOML_WITH_EVERY_CREDENTIAL_SHAPE,
            model_specs_toml=MODEL_SPECS_TOML,
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
            backends_toml=BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT,
            model_specs_toml=MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        backend = required_backend(library)
        assert backend.endpoint == "https://api.acme.example/v1"
        assert backend.unresolved_credentials == {"api_key": ["ACME_API_KEY"]}

    def test_a_backend_that_references_no_variable_has_nothing_unresolved(self, tmp_path: Path) -> None:
        """Ollama's shape: nothing was skipped, so nothing will refuse a call to it."""
        library = load_library(
            tmp_path,
            backends_toml=BACKENDS_TOML_WITH_NO_CREDENTIAL,
            model_specs_toml=MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        backend = required_backend(library)
        assert backend.endpoint == "http://localhost:11434/v1"
        assert backend.unresolved_credentials == {}

    @pytest.mark.parametrize(
        ("model_specs_toml", "expected_vars"),
        [
            (MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL, [ABSENT_VAR]),
            (MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN, [f"{ABSENT_VAR}_A", f"{ABSENT_VAR}_B"]),
        ],
    )
    def test_a_templated_model_spec_keeps_its_text_and_names_its_variables(
        self, tmp_path: Path, model_specs_toml: str, expected_vars: list[str]
    ) -> None:
        """The spec must still validate, so its text is kept; the variables still refuse a call to the backend."""
        library = load_library(tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=model_specs_toml, credentials=CredentialResolution.SKIP)

        backend = required_backend(library)
        assert backend.model_specs["acme-one"].model_id.startswith("${")
        assert backend.unresolved_credentials == {"model_specs": expected_vars}

    def test_a_missing_backend_credential_keeps_the_backend(self, tmp_path: Path) -> None:
        """The keyless boot used to drop this backend, and every model it served with it."""
        library = load_library(
            tmp_path,
            backends_toml=BACKENDS_TOML_WITH_MISSING_CREDENTIAL,
            model_specs_toml=MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        assert required_backend(library).unresolved_credential_vars == [ABSENT_VAR]

    def test_an_enabled_vertexai_backend_mints_no_token_and_touches_no_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Minting the access token is the credential resolution this mode does not do, network call included."""
        make_endpoint_and_api_key = mocker.spy(VertexAIFactory, "make_endpoint_and_api_key")

        library = load_library(
            tmp_path,
            backends_toml=VERTEXAI_BACKENDS_TOML,
            model_specs_toml=VERTEXAI_MODEL_SPECS_TOML,
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
