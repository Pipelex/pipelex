"""A backends document that does not parse is a setup error naming the file.

A `backends_override.toml` with a stray quote is a document the backend library cannot load. The library
refuses it with its own validation class, naming the files it merged, and the boot turns that refusal into
the setup error every other unloadable library gets. The refusal here is produced by the real loader over a
real broken override, so a loader that went back to letting the raw `TomlError` through would fail the
first assertion rather than slip past the boot's clause.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.pipelex import Pipelex
from pipelex.runtime_boot import BACKEND_LIBRARY_REFUSED
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


def _refusal_of_a_broken_override(*, tmp_path: Path) -> Exception:
    base = tmp_path / "backends.toml"
    base.write_text("[internal]\nenabled = true\n", encoding="utf-8")
    override = tmp_path / "backends_override.toml"
    override.write_text('[internal]\nenabled = "true\n', encoding="utf-8")
    library = InferenceBackendLibrary.make_empty()
    with pytest.raises(BACKEND_LIBRARY_REFUSED) as refused:
        library.load(
            secrets_provider=EnvSecretsProvider(),
            backends_library_paths=[base, override],
            backends_dir_path=str(tmp_path / "backends"),
        )
    return refused.value


class TestRuntimeBootBackendsDocumentRefusal:
    def test_a_backends_document_that_does_not_parse_is_a_setup_error_that_names_the_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        refusal = _refusal_of_a_broken_override(tmp_path=tmp_path)
        assert "backends_override.toml" in str(refusal)
        mocker.patch.object(InferenceBackendLibrary, "load", side_effect=refusal)

        Pipelex.teardown_if_needed()
        try:
            with pytest.raises(PipelexSetupError) as raised:
                Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)

            assert "backends_override.toml" in str(raised.value)
            assert raised.value.__cause__ is refusal
        finally:
            mocker.stopall()  # the re-boot below must load the real library
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
