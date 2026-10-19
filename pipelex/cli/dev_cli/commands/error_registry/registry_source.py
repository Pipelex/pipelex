"""Where Pipelex's error registry and its derived files live, and how its source is read.

The registry is authored once, in ``pipelex/errors/registry/pipelex-error-registry.yaml``, without a
version: its snapshot takes Pipelex's own version from ``pyproject.toml``, so the number is written in
one place and every release publishes the registry under it, a pre-release's number in the SemVer form
the registry format requires (:mod:`pipelex.cli.dev_cli.commands.error_registry.registry_version`).
Everything else is derived from the source and the version: the JSON snapshot beside it, the typed
Python of the codes, and the documentation pages under ``docs/errors/``.

The development CLI is not shipped in the wheel, so this module always runs from a checkout and finds
the repository from its own location.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError
from pipelex.cli.dev_cli.commands.error_registry.registry_version import registry_version_of

REPO_ROOT = Path(__file__).resolve().parents[5]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
DOCS_DIR = REPO_ROOT / "docs"

REGISTRY_DIR = REPO_ROOT / "pipelex" / "errors" / "registry"
REGISTRY_SOURCE_PATH = REGISTRY_DIR / "pipelex-error-registry.yaml"
REGISTRY_SNAPSHOT_PATH = REGISTRY_DIR / "pipelex-error-registry.json"
PIPELEX_CODES_PATH = REGISTRY_DIR / "pipelex_codes.py"

# The pages, as paths from the documentation's root: the index, and one page per code beneath it.
PAGES_ROOT = "errors"
INDEX_PAGE = f"{PAGES_ROOT}/index.md"

STANDARD_DIR = Path(__file__).resolve().parent / "standard"
STANDARD_SCHEMA_PATH = STANDARD_DIR / "mthds-error-registry.schema.json"
STANDARD_CORE_SNAPSHOT_PATH = STANDARD_DIR / "mthds-error-registry.json"
STANDARD_RECORD_PATH = STANDARD_DIR / "vendored.toml"


def relative_to_repo(*, path: Path) -> str:
    """A path as a reader of the repository names it, from its root."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses a mapping holding the same key twice, which a YAML loader would otherwise keep silently.

    It also refuses a complex key, a sequence or a mapping written after `?`, which the registry format never
    uses and which no Python mapping can hold, as a load fault rather than an unhashable key's `TypeError`.
    """


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:  # kw-only: ignore
    # A PyYAML constructor, which the loader calls positionally with itself and the node.
    seen: set[Any] = set()
    for key_node, _value_node in node.value:
        if not isinstance(key_node, yaml.ScalarNode):
            msg = "found a key that is a sequence or a mapping, where the registry's keys are plain names"
            raise yaml.constructor.ConstructorError(None, None, msg, key_node.start_mark)
        key: Any = loader.construct_object(key_node, deep=True)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if key in seen:
            msg = f"duplicate key {key!r}"
            raise yaml.constructor.ConstructorError(None, None, msg, key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_registry_source(*, path: Path = REGISTRY_SOURCE_PATH) -> dict[str, Any]:
    """The registry's YAML source, as a mapping.

    Raises:
        ErrorRegistryError: When the file cannot be read, does not parse, holds a key twice or a key that is a
            sequence or a mapping, or is not a mapping.
    """
    try:
        with path.open(encoding="utf-8") as stream:
            loaded: Any = yaml.load(stream, Loader=_UniqueKeyLoader)  # ruff: ignore[unsafe-yaml-load] - the loader is a SafeLoader subclass
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"{relative_to_repo(path=path)} cannot be read: {exc}"
        raise ErrorRegistryError(msg) from exc
    except yaml.YAMLError as exc:
        msg = f"{relative_to_repo(path=path)}: {exc}"
        raise ErrorRegistryError(msg) from exc
    if not isinstance(loaded, dict):
        msg = f"{relative_to_repo(path=path)}: the registry is a mapping of its members"
        raise ErrorRegistryError(msg)
    source: dict[str, Any] = {str(key): value for key, value in cast("dict[Any, Any]", loaded).items()}
    return source


def read_pipelex_version(*, pyproject_path: Path = PYPROJECT_PATH) -> str:
    """Pipelex's version, the `[project].version` of ``pyproject.toml``, which the registry is published under.

    Raises:
        ErrorRegistryError: When ``pyproject.toml`` cannot be read, does not parse or has no version.
    """
    try:
        project: Any = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project", {})
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"{relative_to_repo(path=pyproject_path)} cannot be read: {exc}"
        raise ErrorRegistryError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"{relative_to_repo(path=pyproject_path)} is not valid TOML: {exc}"
        raise ErrorRegistryError(msg) from exc
    version: Any = cast("dict[str, Any]", project).get("version") if isinstance(project, dict) else None
    if not isinstance(version, str):
        msg = f"{relative_to_repo(path=pyproject_path)} has no [project].version"
        raise ErrorRegistryError(msg)
    return version


def read_registry_version(*, pyproject_path: Path = PYPROJECT_PATH) -> str:
    """The version the registry is published under: Pipelex's version, a pre-release's written in SemVer form.

    Raises:
        ErrorRegistryError: When ``pyproject.toml`` has no version, or one the registry cannot be published under.
    """
    package_version = read_pipelex_version(pyproject_path=pyproject_path)
    try:
        return registry_version_of(package_version=package_version)
    except ValueError as exc:
        msg = f"{relative_to_repo(path=pyproject_path)}: {exc}"
        raise ErrorRegistryError(msg) from exc


def compose_registry_document(*, source: dict[str, Any], version: str) -> dict[str, Any]:
    """The registry document the snapshot holds: the version first, then the source's members in their order.

    Raises:
        ErrorRegistryError: When the source writes a version of its own, which only ``pyproject.toml`` holds.
    """
    if "version" in source:
        msg = (
            f"{relative_to_repo(path=REGISTRY_SOURCE_PATH)} writes a version, but the registry takes Pipelex's version from "
            f"{relative_to_repo(path=PYPROJECT_PATH)}: remove it"
        )
        raise ErrorRegistryError(msg)
    return {"version": version, **source}


def render_snapshot_text(*, document: dict[str, Any]) -> str:
    """The JSON snapshot's text: two-space indented, its non-ASCII text kept, and a final newline."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def load_composed_document() -> dict[str, Any]:
    """The registry document composed from the committed source and Pipelex's current version, in its SemVer form."""
    return compose_registry_document(source=load_registry_source(), version=read_registry_version())


def load_json_file(*, path: Path) -> Any:
    """A JSON file's content.

    Raises:
        ErrorRegistryError: When the file cannot be read or is not valid JSON.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"{relative_to_repo(path=path)} cannot be read: {exc}"
        raise ErrorRegistryError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"{relative_to_repo(path=path)} is not valid JSON: {exc}"
        raise ErrorRegistryError(msg) from exc


class VendoredFile(BaseModel):
    """One file of the standard copied here: where it lives in the standard's repository, and its digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str


class VendoredSource(BaseModel):
    """The release or the commit of the standard the vendored files were copied from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    ref: str
    commit: str
    standard_version: str


class VendoredRecord(BaseModel):
    """The record of the standard's files copied here, which ``vendored.toml`` holds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: VendoredSource
    files: dict[str, VendoredFile]


def load_vendored_record(*, path: Path = STANDARD_RECORD_PATH) -> VendoredRecord:
    """The record of the vendored standard files.

    Raises:
        ErrorRegistryError: When the record cannot be read, does not parse or is not such a record.
    """
    try:
        return VendoredRecord.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"{relative_to_repo(path=path)} cannot be read: {exc}"
        raise ErrorRegistryError(msg) from exc
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        msg = f"{relative_to_repo(path=path)} is not a valid record of the vendored standard files: {exc}"
        raise ErrorRegistryError(msg) from exc


def vendored_file_errors(*, record: VendoredRecord, standard_dir: Path = STANDARD_DIR) -> list[str]:
    """The vendored files that are missing or whose content no longer has the digest the record holds."""
    errors: list[str] = []
    for file_name, vendored_file in record.files.items():
        file_path = standard_dir / file_name
        if not file_path.is_file():
            errors.append(f"{relative_to_repo(path=file_path)} is missing, though {relative_to_repo(path=STANDARD_RECORD_PATH)} records it")
            continue
        try:
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"{relative_to_repo(path=file_path)} cannot be read: {exc}")
            continue
        if digest != vendored_file.sha256:
            errors.append(
                f"{relative_to_repo(path=file_path)} has the digest {digest}, not the {vendored_file.sha256} that "
                f"{relative_to_repo(path=STANDARD_RECORD_PATH)} records: the standard's files are copied verbatim and never edited here"
            )
    return errors
