from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.dev_cli.commands.error_registry import registry_version
from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError
from pipelex.cli.dev_cli.commands.error_registry.registry_checks import registry_errors
from pipelex.cli.dev_cli.commands.error_registry.registry_source import (
    DOCS_DIR,
    compose_registry_document,
    load_registry_source,
    read_registry_version,
)
from pipelex.cli.dev_cli.commands.error_registry.registry_version import registry_version_of
from pipelex.errors.registry.registry_document import ErrorRegistryDocument

if TYPE_CHECKING:
    from pathlib import Path

# The module the release workflow's version gate runs as a script on a bare runner.
REGISTRY_VERSION_SCRIPT = registry_version.__file__


class TestRegistryVersion:
    @pytest.mark.parametrize(
        ("package_version", "expected"),
        [
            ("0.88.0", "0.88.0"),
            ("0.88.0a1", "0.88.0-a.1"),
            ("0.88.0b2", "0.88.0-b.2"),
            ("0.88.0rc1", "0.88.0-rc.1"),
            ("1.10.3rc12", "1.10.3-rc.12"),
        ],
    )
    def test_a_pipelex_version_is_written_as_semver(
        self,
        package_version: str,
        expected: str,
        standard_schema: dict[str, Any],
        core_registry: ErrorRegistryDocument,
    ) -> None:
        """A release keeps its number, an alpha, a beta and a release candidate take their SemVer form, which the format accepts."""
        version = registry_version_of(package_version=package_version)
        assert version == expected
        document = compose_registry_document(source=load_registry_source(), version=version)
        errors = registry_errors(document=document, schema=standard_schema, core=core_registry, docs_dir=DOCS_DIR, where="registry")
        assert errors == []
        assert ErrorRegistryDocument.model_validate(document).version == expected

    @pytest.mark.parametrize("package_version", ["0.88", "0.88.0.post1", "0.88.0.dev1", "0.88.0-rc.1", "0.88.0rc", "v0.88.0"])
    def test_a_version_pipelex_never_releases_under_is_refused(self, package_version: str) -> None:
        """Only the forms the release workflows accept are converted; anything else is refused rather than guessed."""
        with pytest.raises(ValueError, match="cannot be published under it"):
            registry_version_of(package_version=package_version)

    def test_the_pyproject_version_is_read_in_its_registry_form(self, tmp_path: Path) -> None:
        """The generator composes the snapshot with the converted version, and names pyproject.toml when it cannot convert it."""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text('[project]\nname = "pipelex"\nversion = "0.88.0rc1"\n', encoding="utf-8")
        assert read_registry_version(pyproject_path=pyproject_path) == "0.88.0-rc.1"
        pyproject_path.write_text('[project]\nname = "pipelex"\nversion = "0.88.0.post1"\n', encoding="utf-8")
        with pytest.raises(ErrorRegistryError, match="cannot be published under it"):
            read_registry_version(pyproject_path=pyproject_path)

    @pytest.mark.parametrize(("package_version", "expected"), [("0.88.0rc1", "0.88.0-rc.1"), ("0.88.0", "0.88.0")])
    def test_the_release_gate_runs_the_conversion_on_a_bare_interpreter(self, package_version: str, expected: str) -> None:
        """The release workflow runs the module with `python3 -I`, which imports nothing of the repository's environment."""
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed, trusted argv
            [sys.executable, "-I", REGISTRY_VERSION_SCRIPT, package_version],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == f"{expected}\n"

    def test_the_release_gate_fails_on_a_version_it_cannot_convert(self) -> None:
        """A version the registry cannot carry stops the gate with a message, rather than comparing an empty string."""
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed, trusted argv
            [sys.executable, "-I", REGISTRY_VERSION_SCRIPT, "0.88.0.dev1"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert "cannot be published under it" in result.stderr
