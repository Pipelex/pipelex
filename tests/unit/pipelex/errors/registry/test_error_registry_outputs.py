from __future__ import annotations

import io
import json
import re
from typing import TYPE_CHECKING, Any

import pytest
import typer
from rich.console import Console

from pipelex.cli.dev_cli.commands.error_registry import error_registry_cmd, registry_outputs
from pipelex.cli.dev_cli.commands.error_registry.error_registry_cmd import (
    check_error_registry_cmd,
    generate_error_registry_cmd,
    write_error_type_redirects_cmd,
)
from pipelex.cli.dev_cli.commands.error_registry.registry_outputs import check_error_registry, orphan_pages, source_errors
from pipelex.cli.dev_cli.commands.error_registry.registry_source import (
    DOCS_DIR,
    REGISTRY_SNAPSHOT_PATH,
    compose_registry_document,
    load_registry_source,
    load_vendored_record,
    read_pipelex_version,
    read_registry_version,
    vendored_file_errors,
)
from pipelex.cli.dev_cli.commands.error_registry.registry_version import registry_version_of
from pipelex.errors.registry.pipelex_codes import PIPELEX_ERROR_PARAMS, PipelexErrorCode
from pipelex.errors.registry.registry_document import load_pipelex_error_registry, read_pipelex_error_registry_snapshot_text

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture

REMEDY = "run `make generate-error-registry` to rewrite them from pipelex/errors/registry/pipelex-error-registry.yaml"


class TestErrorRegistryOutputs:
    def test_every_derived_file_is_what_the_generator_writes(self) -> None:
        """The snapshot, the typed codes and the pages are exactly what the generator writes from the source, with no stray page."""
        checked, errors = check_error_registry()
        assert checked is not None, errors
        assert errors == [], f"the error registry's derived files are stale: {REMEDY}:\n" + "\n".join(errors)

    def test_the_check_command_passes(self) -> None:
        """`pipelex-dev check-error-registry` exits normally on the committed registry."""
        check_error_registry_cmd(quiet=True)

    def test_the_snapshot_carries_pipelex_version(self) -> None:
        """The registry is published under Pipelex's own version, which only pyproject.toml writes, in the form the release gate reads."""
        snapshot = json.loads(REGISTRY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        expected = registry_version_of(package_version=read_pipelex_version())
        assert snapshot["version"] == expected, f"the snapshot's version is not pyproject.toml's: {REMEDY}"
        assert next(iter(snapshot)) == "version"
        assert "version" not in load_registry_source()

    def test_the_shipped_snapshot_loads_into_the_typed_model(self) -> None:
        """The package's snapshot, read through importlib.resources, is the committed one and validates."""
        assert read_pipelex_error_registry_snapshot_text() == REGISTRY_SNAPSHOT_PATH.read_text(encoding="utf-8")
        registry = load_pipelex_error_registry()
        assert registry.prefix == "pipelex"
        assert registry.base_url == "https://docs.pipelex.com/errors"
        assert len(registry.codes) == len(load_registry_source()["codes"])
        assert registry.type_uri(code="pipelex.billing.credit_exhausted") == "https://docs.pipelex.com/errors/pipelex.billing.credit_exhausted"

    def test_every_code_has_its_page_and_its_parameters_model(self) -> None:
        """Each code is a member of PipelexErrorCode, has a parameters model and a page at the path its type URI leads to."""
        registry = load_pipelex_error_registry()
        assert {str(code) for code in PipelexErrorCode} == {entry.code for entry in registry.codes}
        assert set(PIPELEX_ERROR_PARAMS) == set(PipelexErrorCode)
        for entry in registry.codes:
            assert PIPELEX_ERROR_PARAMS[PipelexErrorCode(entry.code)].code == entry.code
            assert entry.page_path == "errors/" + entry.code.replace(".", "/") + ".md"
            assert (DOCS_DIR / entry.page_path).is_file()

    def test_the_vendored_standard_files_are_the_recorded_ones(self) -> None:
        """The standard's schema and core snapshot are copied verbatim, at the digests and the commit vendored.toml records."""
        record = load_vendored_record()
        assert vendored_file_errors(record=record) == []
        assert set(record.files) == {"mthds-error-registry.schema.json", "mthds-error-registry.json"}
        assert re.fullmatch(r"[0-9a-f]{40}", record.source.commit)

    def test_a_hidden_file_under_the_pages_is_no_orphan(self, tmp_path: Path) -> None:
        """A `.DS_Store` a desktop leaves under docs/errors/ is neither reported nor removed; a stray page is."""
        pages_dir = tmp_path / "errors"
        (pages_dir / "pipelex" / ".cache").mkdir(parents=True)
        generated = pages_dir / "index.md"
        stray = pages_dir / "pipelex" / "stray.md"
        for path in (generated, stray, pages_dir / ".DS_Store", pages_dir / "pipelex" / ".DS_Store", pages_dir / "pipelex" / ".cache" / "page.md"):
            path.write_text("text", encoding="utf-8")
        assert orphan_pages(outputs={generated: "text"}, pages_dir=pages_dir) == [stray]


def _source_from(text: str) -> Callable[[Path], Callable[[], dict[str, Any]]]:
    """A composed-document loader reading a source file of this text, written under the test's directory."""

    def loader_in(tmp_path: Path) -> Callable[[], dict[str, Any]]:
        source_path = tmp_path / "registry.yaml"
        source_path.write_text(text, encoding="utf-8")
        return lambda: compose_registry_document(source=load_registry_source(path=source_path), version=read_registry_version())

    return loader_in


def _missing_source(tmp_path: Path) -> Callable[[], dict[str, Any]]:
    return lambda: compose_registry_document(source=load_registry_source(path=tmp_path / "absent.yaml"), version="0.1.0")


def _pyproject_from(text: str) -> Callable[[Path], Callable[[], dict[str, Any]]]:
    """A composed-document loader reading the committed source and a ``pyproject.toml`` of this text."""

    def loader_in(tmp_path: Path) -> Callable[[], dict[str, Any]]:
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(text, encoding="utf-8")
        return lambda: compose_registry_document(source=load_registry_source(), version=read_registry_version(pyproject_path=pyproject_path))

    return loader_in


class TestErrorRegistryFaultsArePrinted:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route the commands' console to a buffer, wide enough that no assertion depends on where Rich wraps."""
        buffer = io.StringIO()
        mocker.patch.object(error_registry_cmd, "get_console", return_value=Console(file=buffer, width=400, force_terminal=False))
        return buffer

    @pytest.mark.parametrize(
        ("loader_in", "expected"),
        [
            (_source_from("codes: [\n"), "registry.yaml: while parsing"),
            (_source_from("prefix: pipelex\nprefix: acme\n"), "duplicate key 'prefix'"),
            (_source_from("- a list\n"), "the registry is a mapping of its members"),
            (_source_from("version: 1.0.0\nprefix: pipelex\n"), "writes a version"),
            (_missing_source, "absent.yaml cannot be read"),
            (_pyproject_from('[project]\nversion = "0.88.0.post1"\n'), "pyproject.toml"),
            (_pyproject_from("[project\n"), "pyproject.toml is not valid TOML"),
            (_pyproject_from('[project]\nname = "pipelex"\n'), "has no [project].version"),
        ],
    )
    def test_a_source_that_does_not_load_is_a_printed_fault(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        console_buffer: io.StringIO,
        loader_in: Callable[[Path], Callable[[], dict[str, Any]]],
        expected: str,
    ) -> None:
        """A source or a version the loaders refuse is reported as a fault, and the generator exits with 1 having written nothing."""
        mocker.patch.object(registry_outputs, "load_composed_document", side_effect=loader_in(tmp_path))
        write_outputs = mocker.patch.object(error_registry_cmd, "write_outputs")
        checked, errors = source_errors()
        assert checked is None
        assert any(expected in error for error in errors), errors
        with pytest.raises(typer.Exit) as exit_info:
            generate_error_registry_cmd(quiet=True)
        assert exit_info.value.exit_code == 1
        write_outputs.assert_not_called()
        assert expected in console_buffer.getvalue()

    @pytest.mark.parametrize(
        ("core_text", "expected"),
        [
            ("{not json", "is not valid JSON"),
            ('{"version": "1.0.0"}', "is not a registry the typed model reads"),
            (None, "cannot be read"),
        ],
    )
    def test_a_core_snapshot_that_does_not_load_is_a_printed_fault(
        self, mocker: MockerFixture, tmp_path: Path, console_buffer: io.StringIO, core_text: str | None, expected: str
    ) -> None:
        """A core snapshot that is not valid JSON, not a registry or not a file is reported as a fault by the check command."""
        core_path = tmp_path / "core.json"
        if core_text is None:
            core_path.mkdir()
        else:
            core_path.write_text(core_text, encoding="utf-8")
        mocker.patch.object(registry_outputs, "STANDARD_CORE_SNAPSHOT_PATH", core_path)
        checked, errors = source_errors()
        assert checked is None
        assert any(expected in error for error in errors), errors
        with pytest.raises(typer.Exit) as exit_info:
            check_error_registry_cmd(quiet=True)
        assert exit_info.value.exit_code == 1
        assert expected in console_buffer.getvalue()

    def test_a_site_without_a_latest_version_is_a_printed_fault(self, tmp_path: Path, console_buffer: io.StringIO) -> None:
        """The redirect command reports a site it cannot write the redirects into, rather than raise."""
        with pytest.raises(typer.Exit) as exit_info:
            write_error_type_redirects_cmd(site_root=tmp_path, quiet=True)
        assert exit_info.value.exit_code == 1
        assert "holds no 'latest' version" in console_buffer.getvalue()
