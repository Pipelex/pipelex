"""The package reaches core only through the published Inference SPI.

Every `pipelex.*` name the package imports, at module level, deferred or for type checking alone, must
be a row of the SPI table in `docs/under-the-hood/inference-backend-plugins.md`, unless it is the
package's own. Deny by default: a new import of anything else turns this red, and the fix is either to
publish the symbol in the table, under a role that names no consumer, or to give the package its own
copy of it. The scan is what lets the package be copied out of this repository as a plugin of its own
and keep working against a published surface.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_REPO_ROOT = _TESTS_ROOT.parent
_PACKAGE_DIR = _REPO_ROOT / "pipelex" / "providers" / "pipelex_hosted"
_PACKAGE_MODULE = "pipelex.providers.pipelex_hosted"
_SPI_PAGE = _REPO_ROOT / "docs" / "under-the-hood" / "inference-backend-plugins.md"

_SPI_ROW = re.compile(r"^\| (?P<symbols>`[^|]+`) \| `(?P<module>[\w.]+)` \| ")
_BACKTICKED = re.compile(r"`([A-Za-z_][\w]*)`")


def _published_symbols() -> set[tuple[str, str]]:
    section = _SPI_PAGE.read_text(encoding="utf-8").split("## The Inference SPI", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    published: set[tuple[str, str]] = set()
    for line in section.splitlines():
        if row := _SPI_ROW.match(line):
            published.update((row["module"], symbol) for symbol in _BACKTICKED.findall(row["symbols"]))
    return published


def _core_imports() -> list[tuple[str, str, str]]:
    """Every `(file, module, symbol)` the package imports from `pipelex` outside itself."""
    imports: list[tuple[str, str, str]] = []
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module is not None and node.module.split(".")[0] == "pipelex":
                if node.module == _PACKAGE_MODULE or node.module.startswith(f"{_PACKAGE_MODULE}."):
                    continue
                imports.extend((path.name, node.module, alias.name) for alias in node.names)
            elif isinstance(node, ast.Import):
                imports.extend((path.name, alias.name, "*") for alias in node.names if alias.name.split(".")[0] == "pipelex")
    return imports


class TestPipelexHostedReachesCoreOnlyThroughTheSpi:
    def test_the_spi_table_parses(self) -> None:
        """Guards the guard: a table the regex stopped reading would let every import through."""
        published = _published_symbols()

        assert ("pipelex.plugins.registrar", "PluginRegistrar") in published
        assert ("pipelex.cogt.inference.service_error_vocabulary", "ServiceErrorCode") in published

    def test_the_package_imports_something_from_core(self) -> None:
        """Guards the guard the other way: a scan that found nothing would pass vacuously."""
        assert _core_imports()

    def test_every_core_import_is_published(self) -> None:
        published = _published_symbols()

        unpublished = sorted(
            f"{file}: from {module} import {symbol}" for file, module, symbol in _core_imports() if (module, symbol) not in published
        )

        assert not unpublished, "Imports outside the Inference SPI table; publish them there or copy them into the package:\n" + "\n".join(
            unpublished
        )

    def test_no_backend_name_constant_is_imported(self) -> None:
        """The package names its own backend; it reads no core constant that does."""
        backend_module = "pipelex.cogt.model_backends.backend"
        assert not [(file, symbol) for file, module, symbol in _core_imports() if module == backend_module and symbol != "InferenceBackend"]
