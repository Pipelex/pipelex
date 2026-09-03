"""`load(lenient=True)` tolerates missing credentials — and nothing else.

The distinction matters because the lenient boot is the one commands like `validate`, `show` and
`--dry-run` use: a config error swallowed there deletes a whole backend from the library, and every
handle it served then fails much later with a far more confusing "model not found".
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType, InferenceBackendLibraryError
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

ABSENT_VAR = "PIPELEX_TEST_ABSENT_VAR_FOR_LENIENCY"

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


class TestBackendLibraryLeniency:
    def _write_config(self, tmp_path: Path, *, backends_toml: str, model_specs_toml: str | None) -> tuple[str, str]:
        backends_dir = tmp_path / "backends"
        backends_dir.mkdir()
        backends_library_path = tmp_path / "backends.toml"
        backends_library_path.write_text(backends_toml)
        if model_specs_toml is not None:
            (backends_dir / "acme.toml").write_text(model_specs_toml)
        return str(backends_library_path), str(backends_dir)

    def _load(self, tmp_path: Path, *, backends_toml: str, model_specs_toml: str | None, lenient: bool) -> InferenceBackendLibrary:
        backends_library_path, backends_dir_path = self._write_config(
            tmp_path,
            backends_toml=backends_toml,
            model_specs_toml=model_specs_toml,
        )
        library = InferenceBackendLibrary.make_empty()
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=[Path(backends_library_path)],
            backends_dir_path=backends_dir_path,
            lenient=lenient,
        )
        return library

    def test_a_well_formed_backend_loads(self, tmp_path: Path) -> None:
        """The control: without this the failure cases below would prove nothing."""
        library = self._load(tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=MODEL_SPECS_TOML, lenient=True)

        assert "acme" in library.root

    @pytest.mark.parametrize("lenient", [True, False])
    def test_an_unknown_key_in_a_local_backend_is_fatal_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        """A stale local TOML — the shape an upgrade leaves behind, since init never overwrites an existing file."""
        with pytest.raises(InferenceBackendLibraryError, match="a_field_we_removed"):
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_UNKNOWN_DEFAULT,
                lenient=lenient,
            )

    @pytest.mark.parametrize("lenient", [True, False])
    def test_an_unknown_per_model_key_in_a_local_backend_is_fatal_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        """A per-model typo used to be sent to the provider as a request header, silently, while the
        real setting stayed unset. It is now a boot error that names the key, the model and the file.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_UNKNOWN_PER_MODEL_KEY,
                lenient=lenient,
            )

        message = str(exc_info.value)
        assert "'max_tokns'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "hyphen" in message

    def test_a_hyphenated_spelling_of_a_known_field_is_fatal_and_names_the_field(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendLibraryError, match=r"'max-tokens'.*'max_tokens'"):
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_NEAR_MISS_PER_MODEL_KEY,
                lenient=False,
            )

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_header_shaped_key_with_a_non_string_value_is_fatal_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        """`x-foo = 3` is an unquoted value, not a header to stringify. The message is the rule's, not pydantic's:
        it names the key, the model and the file, and says the value must be a quoted string.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_NON_STRING_HEADER_VALUE,
                lenient=lenient,
            )

        message = str(exc_info.value)
        assert "'x-foo'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "must be a quoted string" in message
        assert "string_type" not in message

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_header_shaped_key_the_wire_cannot_carry_is_fatal_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        """A quoted TOML key can hold a character no header field name may carry. Such a key used to load
        fine and raise `LocalProtocolError: Illegal header name` on the first inference call instead.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_NAME,
                lenient=lenient,
            )

        message = str(exc_info.value)
        assert "'x-foo bar'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "' '" in message

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_header_value_the_wire_cannot_carry_is_fatal_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        """`x-foo = "trailing "` is valid TOML and the mistake is invisible in the file, which is exactly
        why the error must name it — the HTTP stack otherwise reports it much later, mid-run.
        """
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_VALUE,
                lenient=lenient,
            )

        message = str(exc_info.value)
        assert "'x-foo'" in message
        assert "'acme-one'" in message
        assert "acme.toml" in message
        assert "no leading or trailing whitespace" in message

    def test_a_header_shaped_per_model_key_still_becomes_a_request_header(self, tmp_path: Path) -> None:
        """The regression that matters: `x-portkey-provider` in the local portkey.toml keeps working."""
        library = self._load(tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=MODEL_SPECS_TOML_WITH_HEADER_KEY, lenient=False)

        backend = library.get_inference_backend(backend_name="acme")
        assert backend is not None
        model_spec = backend.model_specs["acme-one"]
        assert model_spec.extra_headers == {"x-portkey-provider": "@openai"}
        assert model_spec.model_id == "acme-one"

    @pytest.mark.parametrize("lenient", [True, False])
    def test_a_missing_per_backend_toml_is_fatal_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        with pytest.raises(InferenceBackendLibraryError, match=r"acme\.toml"):
            self._load(tmp_path, backends_toml=BACKENDS_TOML, model_specs_toml=None, lenient=lenient)

    def test_a_missing_backend_credential_is_skipped_leniently(self, tmp_path: Path) -> None:
        library = self._load(
            tmp_path,
            backends_toml=BACKENDS_TOML_WITH_MISSING_CREDENTIAL,
            model_specs_toml=MODEL_SPECS_TOML,
            lenient=True,
        )

        assert library.root == {}

    def test_a_missing_model_spec_credential_is_skipped_leniently(self, tmp_path: Path) -> None:
        """The placeholder lives in the per-backend TOML, not in backends.toml — same tolerance."""
        library = self._load(
            tmp_path,
            backends_toml=BACKENDS_TOML,
            model_specs_toml=MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL,
            lenient=True,
        )

        assert library.root == {}

    def test_an_unresolvable_model_spec_fallback_pattern_is_skipped_leniently(self, tmp_path: Path) -> None:
        """A fallback pattern whose every candidate is absent is still just a missing credential."""
        library = self._load(
            tmp_path,
            backends_toml=BACKENDS_TOML,
            model_specs_toml=MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN,
            lenient=True,
        )

        assert library.root == {}

    def test_an_unresolvable_model_spec_fallback_pattern_raises_a_credentials_error_when_strict(self, tmp_path: Path) -> None:
        """No single variable name is right when several were tried, but the error still names the backend."""
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            self._load(
                tmp_path,
                backends_toml=BACKENDS_TOML,
                model_specs_toml=MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN,
                lenient=False,
            )

        assert exc_info.value.credentials_error_type is InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN
        assert exc_info.value.backend_name == "acme"

    @pytest.mark.parametrize(
        ("backends_toml", "model_specs_toml"),
        [
            (BACKENDS_TOML_WITH_MISSING_CREDENTIAL, MODEL_SPECS_TOML),
            (BACKENDS_TOML, MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL),
        ],
    )
    def test_a_missing_credential_raises_a_credentials_error_when_strict(
        self,
        tmp_path: Path,
        backends_toml: str,
        model_specs_toml: str,
    ) -> None:
        """Strictly, both placements name the variable — that is what the boot turns into 'set this key'."""
        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            self._load(tmp_path, backends_toml=backends_toml, model_specs_toml=model_specs_toml, lenient=False)

        assert exc_info.value.key_name == ABSENT_VAR
        assert exc_info.value.backend_name == "acme"
