"""An enabled backend still naming the retired `model_specs_section` is refused, not booted with no models."""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryValidationError
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

BACKENDS_TOML_TEMPLATE = """
[pipelex_hosted]
display_name = "Pipelex"
enabled = {enabled}
model_specs_section = "pipelex_hosted_model_specs"
api_key = "sk-not-a-real-key"
"""

COMMENT_ONLY_BACKEND_TOML = "# The model specs of this backend are served remotely.\n"


class TestBackendRetiredModelSpecsSection:
    def _load(self, *, tmp_path: Path, enabled: bool, lenient: bool = False) -> InferenceBackendLibrary:
        backends_dir = tmp_path / "backends"
        backends_dir.mkdir()
        (backends_dir / "pipelex_hosted.toml").write_text(COMMENT_ONLY_BACKEND_TOML)
        base_path = tmp_path / "backends.toml"
        base_path.write_text(BACKENDS_TOML_TEMPLATE.format(enabled=str(enabled).lower()))
        library = InferenceBackendLibrary.make_empty()
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=[base_path],
            backends_dir_path=str(backends_dir),
            lenient=lenient,
        )
        return library

    @pytest.mark.parametrize("lenient", [False, True])
    def test_an_enabled_backend_naming_it_is_refused_in_both_modes(self, tmp_path: Path, lenient: bool) -> None:
        with pytest.raises(InferenceBackendLibraryValidationError) as refused:
            self._load(tmp_path=tmp_path, enabled=True, lenient=lenient)

        message = str(refused.value)
        assert "pipelex_hosted" in message
        assert "model_specs_section" in message
        assert "backends/pipelex_hosted.toml" in message

    def test_a_disabled_backend_naming_it_is_skipped(self, tmp_path: Path) -> None:
        library = self._load(tmp_path=tmp_path, enabled=False)

        assert library.all_enabled_backends() == []
