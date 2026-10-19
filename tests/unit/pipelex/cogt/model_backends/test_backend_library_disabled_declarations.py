"""A disabled backend's file tells the deck which models this deployment knows of but does not serve, and never stops a boot."""

from pathlib import Path

import pytest

from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from tests.unit.pipelex.cogt.model_backends.test_data import BackendLibraryTomls


class TestBackendLibraryDisabledDeclarations:
    @pytest.mark.parametrize(
        ("_topic", "disabled_file_bytes", "expected_cataloged"),
        [
            (
                "declares_a_model",
                BackendLibraryTomls.DISABLED_MODEL_SPECS_TOML.encode(),
                {"acme-one": [ModelType.LLM], "dormant-one": [ModelType.LLM]},
            ),
            ("not_utf8", b'["dormant-one"]\nmodel_id = "\xff"\n', {"acme-one": [ModelType.LLM]}),
            ("not_toml", b"[dormant-one\n", {"acme-one": [ModelType.LLM]}),
            ("missing", None, {"acme-one": [ModelType.LLM]}),
        ],
    )
    def test_a_disabled_backend_s_file_never_stops_the_boot(
        self, tmp_path: Path, _topic: str, disabled_file_bytes: bytes | None, expected_cataloged: dict[str, list[ModelType]]
    ) -> None:
        """A disabled backend's models are cataloged, never served, and a file of its that cannot be read declares nothing."""
        backends_dir = tmp_path / "backends"
        backends_dir.mkdir()
        if disabled_file_bytes is not None:
            (backends_dir / "dormant.toml").write_bytes(disabled_file_bytes)
        (backends_dir / "acme.toml").write_text(BackendLibraryTomls.MODEL_SPECS_TOML)
        backends_library_path = tmp_path / "backends.toml"
        backends_library_path.write_text(BackendLibraryTomls.BACKENDS_TOML_WITH_A_DISABLED_BACKEND)
        library = InferenceBackendLibrary.make_empty()

        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=[backends_library_path],
            backends_dir_path=str(backends_dir),
            credentials=CredentialResolution.SKIP,
        )

        assert library.list_backend_names() == ["acme"]
        assert library.get_cataloged_types_by_handle() == expected_cataloged
