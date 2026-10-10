"""A malformed backend configuration is fatal whether the load resolves credentials or not.

A config error swallowed by the keyless boot would delete a whole backend from the library, and every
handle it served would then fail much later with a far more confusing "model not found". A placeholder
in a field that describes the model is malformed in the same way: the keyless boot could not resolve
it, so a load that resolved it would give a verdict the keyless one cannot.
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import (
    InferenceBackendCredentialsError,
    InferenceBackendCredentialsErrorType,
    InferenceBackendLibraryError,
    InferenceBackendLibraryValidationError,
)
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_type import ModelType
from tests.helpers.backend_library_loading import BOTH_MODES, load_library, required_backend
from tests.helpers.recording_secrets_provider import RecordingSecretsProvider
from tests.unit.pipelex.cogt.model_backends.test_data import LITERAL_FIELD_VAR, BackendLibraryTomls


class TestMalformedConfigurationIsFatalInBothModes:
    def test_a_well_formed_backend_loads(self, tmp_path: Path) -> None:
        """The control: without this the failure cases below would prove nothing."""
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.SKIP,
        )

        assert "acme" in library.root

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_an_unknown_key_in_a_local_backend_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        """A stale local TOML — the shape an upgrade leaves behind, since init never overwrites an existing file."""
        with pytest.raises(InferenceBackendLibraryError, match="a_field_we_removed"):
            load_library(
                tmp_path,
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_UNKNOWN_DEFAULT,
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
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_UNKNOWN_PER_MODEL_KEY,
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
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_NEAR_MISS_PER_MODEL_KEY,
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
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_NON_STRING_HEADER_VALUE,
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
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_NAME,
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
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_VALUE,
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
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML_WITH_HEADER_KEY,
            credentials=CredentialResolution.REQUIRE,
        )

        model_spec = required_backend(library).get_model_spec(model_type=ModelType.LLM, handle="acme-one")
        assert model_spec is not None
        assert model_spec.extra_headers == {"x-portkey-provider": "@openai"}
        assert model_spec.model_id == "acme-one"

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    def test_a_missing_per_backend_toml_is_fatal_in_both_modes(self, tmp_path: Path, credentials: CredentialResolution) -> None:
        with pytest.raises(InferenceBackendLibraryError, match=r"acme\.toml"):
            load_library(tmp_path, backends_toml=BackendLibraryTomls.BACKENDS_TOML, model_specs_toml=None, credentials=credentials)

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    @pytest.mark.parametrize(
        ("backends_toml", "model_specs_toml", "field_name", "valid_value"),
        [
            pytest.param(
                BackendLibraryTomls.BACKENDS_TOML,
                BackendLibraryTomls.MODEL_SPECS_TOML_WITH_A_TEMPLATED_MODEL_TYPE,
                "model_type",
                "llm",
                id="model_type_in_defaults",
            ),
            pytest.param(
                BackendLibraryTomls.BACKENDS_TOML,
                BackendLibraryTomls.MODEL_SPECS_TOML_WITH_A_TEMPLATED_THINKING_MODE,
                "thinking_mode",
                "none",
                id="thinking_mode_on_a_model",
            ),
            pytest.param(
                BackendLibraryTomls.BACKENDS_TOML_WITH_A_TEMPLATED_CONSTRAINT,
                BackendLibraryTomls.MODEL_SPECS_TOML,
                "listed_constraints",
                "temperature_unsupported",
                id="listed_constraints_on_a_backend",
            ),
        ],
    )
    def test_a_placeholder_in_a_field_describing_the_model_is_fatal_in_both_modes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        credentials: CredentialResolution,
        backends_toml: str,
        model_specs_toml: str,
        field_name: str,
        valid_value: str,
    ) -> None:
        """The variable resolves to a valid value, so only the rule refuses it, on the load that could resolve it too."""
        monkeypatch.setenv(LITERAL_FIELD_VAR, valid_value)

        with pytest.raises(InferenceBackendLibraryValidationError) as exc_info:
            load_library(tmp_path, backends_toml=backends_toml, model_specs_toml=model_specs_toml, credentials=credentials)

        message = str(exc_info.value)
        assert f"'{field_name}' references {LITERAL_FIELD_VAR}" in message
        assert "write it literally" in message

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    @pytest.mark.parametrize(
        ("backends_toml", "field_name"),
        [
            pytest.param(BackendLibraryTomls.BACKENDS_TOML_WITH_A_TEMPLATED_KEY_IN_A_LIST, "api_key", id="api_key_in_a_list"),
            pytest.param(BackendLibraryTomls.BACKENDS_TOML_WITH_A_TEMPLATED_EXTRA_CONFIG_TABLE, "extra_config", id="extra_config_as_a_string"),
        ],
    )
    def test_a_templated_field_of_the_wrong_type_is_fatal_in_both_modes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, credentials: CredentialResolution, backends_toml: str, field_name: str
    ) -> None:
        """A keyless load strips a templated field, but not before its type is checked, so stripping hides no malformed field."""
        monkeypatch.setenv(LITERAL_FIELD_VAR, "sk-not-a-real-key")

        with pytest.raises(InferenceBackendLibraryValidationError) as exc_info:
            load_library(tmp_path, backends_toml=backends_toml, model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML, credentials=credentials)

        message = str(exc_info.value)
        assert "Invalid inference backend 'acme'" in message
        assert field_name in message

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    @pytest.mark.parametrize(
        ("backends_toml", "model_specs_toml", "var_name"),
        [
            pytest.param(
                BackendLibraryTomls.BACKENDS_TOML_WITH_AN_UNKNOWN_PREFIX, BackendLibraryTomls.MODEL_SPECS_TOML, "ACME_API_KEY", id="backend_table"
            ),
            pytest.param(
                BackendLibraryTomls.BACKENDS_TOML, BackendLibraryTomls.MODEL_SPECS_TOML_WITH_AN_UNKNOWN_PREFIX, "ACME_MODEL", id="model_spec"
            ),
            pytest.param(
                BackendLibraryTomls.BACKENDS_TOML,
                BackendLibraryTomls.MODEL_SPECS_TOML_WITH_AN_UNKNOWN_PREFIX_IN_A_LITERAL_FIELD,
                "ACME_SDK",
                id="model_spec_literal_field",
            ),
        ],
    )
    def test_an_unknown_placeholder_prefix_is_fatal_in_both_modes(
        self, tmp_path: Path, credentials: CredentialResolution, backends_toml: str, model_specs_toml: str, var_name: str
    ) -> None:
        """A load that only names its variables refuses a mistyped prefix as the load that resolves them does."""
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=backends_toml,
                model_specs_toml=model_specs_toml,
                credentials=credentials,
                secrets_provider=RecordingSecretsProvider.make_credentialed(),
            )

        assert exc_info.value.credentials_error_type is InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX
        assert exc_info.value.key_name == var_name
