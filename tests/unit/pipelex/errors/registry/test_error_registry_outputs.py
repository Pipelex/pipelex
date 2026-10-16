from __future__ import annotations

import json
import re

from pipelex.cli.dev_cli.commands.error_registry.error_registry_cmd import check_error_registry_cmd
from pipelex.cli.dev_cli.commands.error_registry.registry_outputs import check_error_registry
from pipelex.cli.dev_cli.commands.error_registry.registry_source import (
    DOCS_DIR,
    REGISTRY_SNAPSHOT_PATH,
    load_registry_source,
    load_vendored_record,
    read_pipelex_version,
    vendored_file_errors,
)
from pipelex.errors.registry.pipelex_codes import PIPELEX_ERROR_PARAMS, PipelexErrorCode
from pipelex.errors.registry.registry_document import load_pipelex_error_registry, read_pipelex_error_registry_snapshot_text

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
        """The registry is published under Pipelex's own version, which only pyproject.toml writes."""
        snapshot = json.loads(REGISTRY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert snapshot["version"] == read_pipelex_version(), f"the snapshot's version is not pyproject.toml's: {REMEDY}"
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
