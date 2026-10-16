"""The files derived from Pipelex's error registry: how they are rendered, written and checked.

From the YAML source and Pipelex's version come, and only come:

- the JSON snapshot, ``pipelex/errors/registry/pipelex-error-registry.json``, which the package ships and
  every release publishes as an asset;
- the typed Python of the codes, ``pipelex/errors/registry/pipelex_codes.py``;
- the documentation pages, ``docs/errors/index.md`` and one page per code beneath it.

The generator owns ``docs/errors/`` whole: a page there that it does not write is removed when it writes,
and reported when it checks. A hidden file, such as ``.DS_Store``, is no page, and is left alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.cli.dev_cli.commands.error_registry.codes_generator import render_pipelex_codes
from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError
from pipelex.cli.dev_cli.commands.error_registry.pages_generator import render_pages
from pipelex.cli.dev_cli.commands.error_registry.registry_checks import registry_errors
from pipelex.cli.dev_cli.commands.error_registry.registry_source import (
    DOCS_DIR,
    PAGES_ROOT,
    PIPELEX_CODES_PATH,
    REGISTRY_SNAPSHOT_PATH,
    REGISTRY_SOURCE_PATH,
    STANDARD_CORE_SNAPSHOT_PATH,
    STANDARD_SCHEMA_PATH,
    load_composed_document,
    load_json_file,
    load_vendored_record,
    relative_to_repo,
    render_snapshot_text,
    vendored_file_errors,
)
from pipelex.errors.registry.registry_document import ErrorRegistryDocument

if TYPE_CHECKING:
    from pathlib import Path


class RegistryOutputsReport(BaseModel):
    """What a write of the derived files did, each file named from the repository's root."""

    model_config = ConfigDict(frozen=True)

    written: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class CheckedRegistry(BaseModel):
    """A registry that passed every check of its own, with the document its snapshot holds."""

    model_config = ConfigDict(frozen=True)

    document: dict[str, Any]
    registry: ErrorRegistryDocument
    core: ErrorRegistryDocument


def load_core_registry() -> ErrorRegistryDocument:
    """The MTHDS core registry, from the snapshot vendored from the standard."""
    try:
        return ErrorRegistryDocument.model_validate(load_json_file(path=STANDARD_CORE_SNAPSHOT_PATH))
    except ValidationError as exc:
        msg = f"{relative_to_repo(path=STANDARD_CORE_SNAPSHOT_PATH)} is not a registry the typed model reads: {exc}"
        raise ErrorRegistryError(msg) from exc


def source_errors() -> tuple[CheckedRegistry | None, list[str]]:
    """The faults of the registry's source and of the standard's vendored files, or the checked registry when there are none."""
    errors = vendored_file_errors(record=load_vendored_record())
    if errors:
        return None, errors
    schema: Any = load_json_file(path=STANDARD_SCHEMA_PATH)
    if not isinstance(schema, dict):
        return None, [f"{relative_to_repo(path=STANDARD_SCHEMA_PATH)} is not a JSON Schema"]
    core = load_core_registry()
    document = load_composed_document()
    errors = registry_errors(
        document=document,
        schema=schema,  # pyright: ignore[reportUnknownArgumentType]
        core=core,
        docs_dir=DOCS_DIR,
        where=relative_to_repo(path=REGISTRY_SOURCE_PATH),
    )
    if errors:
        return None, errors
    registry = ErrorRegistryDocument.model_validate(document)
    return CheckedRegistry(document=document, registry=registry, core=core), []


def render_outputs(*, checked: CheckedRegistry) -> dict[Path, str]:
    """Every derived file's text, by its path."""
    outputs: dict[Path, str] = {
        REGISTRY_SNAPSHOT_PATH: render_snapshot_text(document=checked.document),
        PIPELEX_CODES_PATH: render_pipelex_codes(registry=checked.registry),
    }
    for page, text in render_pages(registry=checked.registry).items():
        outputs[DOCS_DIR / page] = text
    return outputs


def orphan_pages(*, outputs: dict[Path, str], pages_dir: Path = DOCS_DIR / PAGES_ROOT) -> list[Path]:
    """The pages under ``docs/errors/`` that the generator does not write.

    A hidden file, or a file in a hidden directory, is no page: MkDocs skips it, and a file a desktop or an
    editor leaves there, such as ``.DS_Store``, is neither reported nor removed.
    """
    if not pages_dir.is_dir():
        return []
    orphans: list[Path] = []
    for path in sorted(pages_dir.rglob("*")):
        if not path.is_file() or path in outputs:
            continue
        if any(part.startswith(".") for part in path.relative_to(pages_dir).parts):
            continue
        orphans.append(path)
    return orphans


def stale_output_errors(*, outputs: dict[Path, str]) -> list[str]:
    """The derived files that are missing or differ from what the generator writes, and the pages it does not write."""
    errors: list[str] = []
    for path, text in outputs.items():
        if not path.is_file():
            errors.append(f"{relative_to_repo(path=path)} is missing")
        elif path.read_text(encoding="utf-8") != text:
            errors.append(f"{relative_to_repo(path=path)} is not what the generator writes from the registry")
    errors.extend(f"{relative_to_repo(path=path)} is not a page of the registry" for path in orphan_pages(outputs=outputs))
    return errors


def write_outputs(*, outputs: dict[Path, str]) -> RegistryOutputsReport:
    """Write every derived file that differs, and remove the pages under ``docs/errors/`` the generator does not write."""
    written: list[str] = []
    unchanged: list[str] = []
    removed: list[str] = []
    for path, text in outputs.items():
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            unchanged.append(relative_to_repo(path=path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(relative_to_repo(path=path))
    for path in orphan_pages(outputs=outputs):
        path.unlink()
        removed.append(relative_to_repo(path=path))
    pages_dir = DOCS_DIR / PAGES_ROOT
    for directory in sorted((path for path in pages_dir.rglob("*") if path.is_dir()), key=lambda found: len(found.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    return RegistryOutputsReport(written=written, unchanged=unchanged, removed=removed)


def check_error_registry() -> tuple[CheckedRegistry | None, list[str]]:
    """Every fault of the registry: its source's, the vendored files', and every derived file that is stale."""
    checked, errors = source_errors()
    if checked is None:
        return None, errors
    return checked, stale_output_errors(outputs=render_outputs(checked=checked))


def summary_line(*, checked: CheckedRegistry) -> str:
    """The one line that names the registry, its version and its size."""
    registry = checked.registry
    return (
        f"Pipelex error registry {registry.version} ({relative_to_repo(path=REGISTRY_SOURCE_PATH)}): "
        f"{len(registry.codes)} codes in {len(registry.families)} families under the prefix {registry.prefix}, "
        f"checked against the MTHDS core registry {checked.core.version}"
    )
