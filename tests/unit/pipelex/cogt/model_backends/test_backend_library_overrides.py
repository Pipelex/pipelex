"""`backends_override.toml` layers over `backends.toml`: enabled flips, the rest of the table survives."""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryNotFoundError, InferenceBackendLibraryValidationError
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

BACKENDS_TOML = """
[acme]
display_name = "Acme"
enabled = false
api_key = "sk-not-a-real-key"

[other]
display_name = "Other"
enabled = true
api_key = "sk-not-a-real-key"
"""

MODEL_SPECS_TOML = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["one"]
model_id = "one"
"""


class TestBackendLibraryOverrides:
    def _write_base(self, tmp_path: Path) -> tuple[Path, Path]:
        backends_dir = tmp_path / "backends"
        backends_dir.mkdir()
        (backends_dir / "acme.toml").write_text(MODEL_SPECS_TOML)
        (backends_dir / "other.toml").write_text(MODEL_SPECS_TOML)
        base_path = tmp_path / "backends.toml"
        base_path.write_text(BACKENDS_TOML)
        return base_path, backends_dir

    def _load(self, *, paths: list[Path], backends_dir: Path, include_disabled: bool = False) -> InferenceBackendLibrary:
        library = InferenceBackendLibrary.make_empty()
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=paths,
            backends_dir_path=str(backends_dir),
            include_disabled=include_disabled,
        )
        return library

    def test_the_base_alone_is_what_it_was(self, tmp_path: Path) -> None:
        """The control: an absent override changes nothing."""
        base_path, backends_dir = self._write_base(tmp_path)

        library = self._load(paths=[base_path, tmp_path / "backends_override.toml"], backends_dir=backends_dir)

        assert library.all_enabled_backends() == ["other"]

    def test_an_override_enables_a_backend_and_keeps_the_rest_of_its_table(self, tmp_path: Path) -> None:
        base_path, backends_dir = self._write_base(tmp_path)
        override_path = tmp_path / "backends_override.toml"
        override_path.write_text("[acme]\nenabled = true\n")

        library = self._load(paths=[base_path, override_path], backends_dir=backends_dir)

        assert library.all_enabled_backends() == ["acme", "other"]
        acme = library.get_inference_backend("acme")
        assert acme is not None
        assert acme.api_key == "sk-not-a-real-key"

    def test_an_override_disables_a_backend(self, tmp_path: Path) -> None:
        base_path, backends_dir = self._write_base(tmp_path)
        override_path = tmp_path / "backends_override.toml"
        override_path.write_text("[other]\nenabled = false\n")

        library = self._load(paths=[base_path, override_path], backends_dir=backends_dir)

        assert library.all_enabled_backends() == []

    def test_the_last_override_wins(self, tmp_path: Path) -> None:
        """Global then project: the project's file is the last word."""
        base_path, backends_dir = self._write_base(tmp_path)
        global_override = tmp_path / "global_override.toml"
        global_override.write_text("[acme]\nenabled = true\n[other]\nenabled = false\n")
        project_override = tmp_path / "project_override.toml"
        project_override.write_text("[other]\nenabled = true\n")

        library = self._load(paths=[base_path, global_override, project_override], backends_dir=backends_dir)

        assert library.all_enabled_backends() == ["acme", "other"]

    def test_a_missing_base_is_not_found_even_when_an_override_exists(self, tmp_path: Path) -> None:
        _, backends_dir = self._write_base(tmp_path)
        absent_base = tmp_path / "absent" / "backends.toml"
        override_path = tmp_path / "backends_override.toml"
        override_path.write_text("[acme]\nenabled = true\n")

        with pytest.raises(InferenceBackendLibraryNotFoundError) as refused:
            self._load(paths=[absent_base, override_path], backends_dir=backends_dir)

        assert str(absent_base) in str(refused.value)

    def test_a_refusal_names_the_base_and_the_override_that_was_read(self, tmp_path: Path) -> None:
        """The user edits one of these files to fix it, so the message has to say which were merged."""
        base_path, backends_dir = self._write_base(tmp_path)
        override_path = tmp_path / "backends_override.toml"
        override_path.write_text("[acme]\nenabled = 'not-a-bool'\n")
        absent_override = tmp_path / "absent_override.toml"

        with pytest.raises(InferenceBackendLibraryValidationError) as refused:
            self._load(paths=[base_path, override_path, absent_override], backends_dir=backends_dir)

        message = str(refused.value)
        assert str(base_path) in message
        assert str(override_path) in message
        assert str(absent_override) not in message
