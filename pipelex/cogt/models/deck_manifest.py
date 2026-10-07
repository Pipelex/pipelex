"""Kit manifests: detect when the kit-managed files of an installation have drifted from the kit-shipped templates.

``pipelex update`` manages two areas of an installed configuration, each a ``KitManagedArea`` with its own
manifest file in its own directory: the model deck, and the one backend file the kit owns, the internal
backend's ``internal.toml``. A manifest pins, for one install of an area, the kit version that produced it and
the SHA-256 of each managed file at install/update time. It enables three independent signals:

- Manifest's ``kit_version`` vs the running ``pipelex`` version → behind upstream.
- Manifest's per-file hash vs the installed file's actual hash → user has locally edited a managed file.
- Kit content vs installed content → upstream changed.

In the deck, numbered files (``<digits>_*.toml``, e.g. ``1_llm_deck.toml``) are pipelex-managed. Anything
else is left alone — including ``x_custom_*.toml`` overrides (the recommended escape hatch) and any other
project-local additions (e.g. a cookbook's preset file). In the backends directory only ``internal.toml`` is
managed, because it declares the software-only models open Pipelex ships and an existing install must receive
the ones a release adds: every other backend file is the user's, which ``pipelex update`` never touches
(``pipelex init``, a full reset, rewrites the ones the kit ships).
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.package_utils import get_package_version

MANIFEST_FILENAME = ".kit_manifest.json"
# The one backend file ``pipelex update`` manages: the internal backend's, which declares the models open Pipelex ships.
MANAGED_BACKEND_FILENAME = f"{PipelexBackend.INTERNAL}.toml"


class KitManagedArea(StrEnum):
    """A directory of an installed configuration whose kit-shipped files ``pipelex update`` manages, each with its own manifest."""

    DECK = "deck"
    BACKENDS = "backends"

    @property
    def display_name(self) -> str:
        match self:
            case KitManagedArea.DECK:
                return "Model deck"
            case KitManagedArea.BACKENDS:
                return "Internal backend"

    def is_managed_filename(self, *, filename: str) -> bool:
        """Whether ``pipelex update`` manages a file of this name in this area's directory."""
        match self:
            case KitManagedArea.DECK:
                return _is_managed_deck_filename(filename)
            case KitManagedArea.BACKENDS:
                return filename == MANAGED_BACKEND_FILENAME


class DeckFileStatus(StrEnum):
    """Per-file sync status between an installed kit-managed area and the kit-shipped templates."""

    UP_TO_DATE = "up_to_date"
    KIT_ADDED = "kit_added"
    KIT_REMOVED = "kit_removed"
    CLEAN_BEHIND = "clean_behind"
    LOCALLY_MODIFIED = "locally_modified"

    @property
    def needs_action(self) -> bool:
        """True when an `update` run would touch this file."""
        match self:
            case DeckFileStatus.UP_TO_DATE:
                return False
            case DeckFileStatus.KIT_ADDED | DeckFileStatus.KIT_REMOVED | DeckFileStatus.CLEAN_BEHIND | DeckFileStatus.LOCALLY_MODIFIED:
                return True


class DeckManifest(BaseModel):
    """Persisted record of the kit version and per-file hashes captured at install/update time."""

    model_config = ConfigDict(extra="forbid")

    kit_version: str
    files: dict[str, str] = Field(default_factory=dict)


class DeckSyncReport(BaseModel):
    """Result of comparing an installed kit-managed area's directory to the currently shipping kit."""

    model_config = ConfigDict(extra="forbid")

    kit_version: str
    installed_kit_version: str | None
    manifest_present: bool
    files: dict[str, DeckFileStatus] = Field(default_factory=dict)

    def is_clean(self) -> bool:
        """True when no file needs any action and the manifest is in sync with the kit version."""
        if not self.manifest_present:
            return False
        if self.installed_kit_version != self.kit_version:
            return False
        return all(status == DeckFileStatus.UP_TO_DATE for status in self.files.values())

    def files_with_status(self, status: DeckFileStatus) -> list[str]:
        return sorted(name for name, file_status in self.files.items() if file_status == status)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path) -> str:
    return compute_sha256(path.read_bytes())


def kit_deck_dir() -> Path:
    """Return the kit's shipped deck directory as a real filesystem path.

    Mirrors the conversion done in ``pipelex/cli/commands/init/command.py:228`` so we read the same
    files that ``pipelex init`` copies.
    """
    return Path(str(get_kit_configs_dir())) / "inference" / "deck"


def kit_backends_dir() -> Path:
    """Return the kit's shipped backends directory as a real filesystem path, the way ``kit_deck_dir`` does for the deck."""
    return Path(str(get_kit_configs_dir())) / "inference" / "backends"


def kit_area_dir(*, area: KitManagedArea) -> Path:
    """The kit's shipped directory for an area."""
    match area:
        case KitManagedArea.DECK:
            return kit_deck_dir()
        case KitManagedArea.BACKENDS:
            return kit_backends_dir()


def _is_managed_deck_filename(filename: str) -> bool:
    """True for files that follow the pipelex-managed numbered convention.

    Only ``<digits>_*.toml`` filenames (e.g., ``1_llm_deck.toml``) are pipelex-managed.
    Everything else is left untouched: ``x_custom_*.toml`` overrides, project-local additions
    like ``cookbook.toml``, and non-TOML files (e.g. an accidental ``.DS_Store``).
    """
    if not filename.endswith(".toml"):
        return False
    head, sep, _ = filename.partition("_")
    return bool(sep) and head.isdigit()


def list_managed_kit_files(*, area: KitManagedArea) -> dict[str, str]:
    """Hash every managed file of an area shipped in the current pipelex wheel."""
    kit_dir = kit_area_dir(area=area)
    return {
        entry.name: compute_file_sha256(entry)
        for entry in sorted(kit_dir.iterdir())
        if entry.is_file() and area.is_managed_filename(filename=entry.name)
    }


def list_managed_installed_files(installed_dir: Path, *, area: KitManagedArea) -> dict[str, str]:
    """Hash every managed file of an area present in the user's installed directory for it."""
    if not installed_dir.is_dir():
        return {}
    return {
        entry.name: compute_file_sha256(entry)
        for entry in sorted(installed_dir.iterdir())
        if entry.is_file() and area.is_managed_filename(filename=entry.name)
    }


def compute_kit_manifest(*, area: KitManagedArea) -> DeckManifest:
    """Build the manifest that should be written for an area after a fresh install or successful update."""
    return DeckManifest(kit_version=get_package_version(), files=list_managed_kit_files(area=area))


def stamp_kit_manifests(*, inference_dir: Path) -> None:
    """Write both areas' manifests for an ``inference/`` directory whose managed files were just copied from the kit.

    For the installers that replace every kit file (``pipelex init``, ``pipelex-agent init``), so a later ``pipelex
    update`` tells a file the user edited from one the kit moved on.
    """
    for area in KitManagedArea:
        write_manifest(compute_kit_manifest(area=area), installed_dir=inference_dir / area)


def stamp_missing_kit_manifests(*, inference_dir: Path) -> None:
    """Write the manifest of each area of an ``inference/`` directory that has none, and leave a recorded one alone.

    For the first boot's fill of the home configuration directory, which copies only the kit files the home lacks:
    a manifest already there records the install the area's files came from, and it stays the baseline ``pipelex
    update`` compares against.
    """
    for area in KitManagedArea:
        installed_dir = inference_dir / area
        if not manifest_path(installed_dir).exists():
            write_manifest(compute_kit_manifest(area=area), installed_dir=installed_dir)


def manifest_path(installed_dir: Path) -> Path:
    return installed_dir / MANIFEST_FILENAME


def read_manifest(installed_dir: Path) -> DeckManifest | None:
    """Return the persisted manifest, or ``None`` when absent or unreadable.

    A corrupt manifest is treated as missing — the caller will warn the user and offer to rebuild it.
    """
    target = manifest_path(installed_dir)
    if not path_exists(str(target)):
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return DeckManifest.model_validate(payload)
    except ValueError:
        return None


def write_manifest(manifest: DeckManifest, *, installed_dir: Path) -> None:
    """Persist the manifest, creating the area's directory if needed."""
    installed_dir.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump()
    target = manifest_path(installed_dir)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_deck_stale_fast(deck_dir: Path) -> bool:
    """Boot-path check: one file read, one string compare. No hashing.

    Returns True (stale) when the manifest is missing or its ``kit_version`` is strictly older than
    the running ``pipelex``. Two cases must NOT trigger the warn:

    - exact match (incl. when one side carries a pre-release/build suffix and the other doesn't);
    - downgrade (manifest newer than the installed package) — the user has presumably pinned
      pipelex deliberately, and updating the deck backwards is rarely what they want.
    """
    manifest = read_manifest(deck_dir)
    if manifest is None:
        return True
    return _is_manifest_older(manifest.kit_version, current_version=get_package_version())


def _is_manifest_older(manifest_version: str, *, current_version: str) -> bool:
    """True iff the manifest's recorded core version is strictly older than the installed package.

    Compares semver cores (``X.Y.Z``) ignoring pre-release/build metadata so that an editable build
    versioned ``0.25.0+localdev`` does not appear stale against a stable ``0.25.0`` manifest. Falls
    back to literal string inequality on parse failure (rare, conservative).
    """
    manifest_parts = _try_parse_version(manifest_version)
    current_parts = _try_parse_version(current_version)
    if manifest_parts is None or current_parts is None:
        return manifest_version != current_version
    return manifest_parts < current_parts


def _try_parse_version(version: str) -> tuple[int, ...] | None:
    """Parse a SemVer-ish string's core into a comparable tuple. Returns ``None`` on any failure.

    Strips both the pre-release suffix (``-rc1``) and the build metadata suffix (``+localbuild``).
    """
    core = version.split("+", 1)[0].split("-", 1)[0]
    pieces = core.split(".")
    try:
        return tuple(int(piece) for piece in pieces)
    except ValueError:
        return None


def status_rich_label(status: DeckFileStatus) -> str:
    """Human-friendly Rich-markup label used by both the doctor report and the update plan table."""
    match status:
        case DeckFileStatus.UP_TO_DATE:
            return "[green]up-to-date[/green]"
        case DeckFileStatus.KIT_ADDED:
            return "[green]new[/green]"
        case DeckFileStatus.KIT_REMOVED:
            return "[yellow]removed upstream[/yellow]"
        case DeckFileStatus.CLEAN_BEHIND:
            return "[yellow]behind[/yellow]"
        case DeckFileStatus.LOCALLY_MODIFIED:
            return "[red]locally modified[/red]"


def suggest_x_custom_filename(numbered_filename: str) -> str:
    """Suggest the right ``x_custom_*.toml`` companion for a numbered deck file.

    Example: ``2_img_gen_deck.toml`` → ``x_custom_img_gen_deck.toml``. The convention is to drop
    the leading ``N_`` prefix and prepend ``x_custom_``.
    """
    head, _, tail = numbered_filename.partition("_")
    if not tail or not head.isdigit():
        return "x_custom_*.toml"
    return f"x_custom_{tail}"


def compute_sync_report(installed_dir: Path, *, area: KitManagedArea) -> DeckSyncReport:
    """Full per-file diff between an installed area and the running pipelex's kit.

    This walks every managed file in either side and assigns it a ``DeckFileStatus``. Cost is one
    SHA-256 per file — only call from ``pipelex update`` and ``pipelex doctor``, never on the boot path.
    """
    kit_files = list_managed_kit_files(area=area)
    installed_files = list_managed_installed_files(installed_dir, area=area)
    manifest = read_manifest(installed_dir)
    manifest_files: dict[str, str] = manifest.files if manifest is not None else {}

    all_filenames = set(kit_files) | set(installed_files)
    file_statuses: dict[str, DeckFileStatus] = {}
    for filename in all_filenames:
        kit_hash = kit_files.get(filename)
        installed_hash = installed_files.get(filename)
        manifest_hash = manifest_files.get(filename)

        if kit_hash is not None and installed_hash is None:
            file_statuses[filename] = DeckFileStatus.KIT_ADDED
            continue
        if kit_hash is None and installed_hash is not None:
            file_statuses[filename] = DeckFileStatus.KIT_REMOVED
            continue

        # Both present from here on.
        if manifest_hash is not None:
            if manifest_hash != installed_hash:
                file_statuses[filename] = DeckFileStatus.LOCALLY_MODIFIED
            elif manifest_hash != kit_hash:
                file_statuses[filename] = DeckFileStatus.CLEAN_BEHIND
            else:
                file_statuses[filename] = DeckFileStatus.UP_TO_DATE
            continue

        # No manifest entry — treat untouched files as up-to-date, divergent ones as locally modified
        # (we have no provenance proof, so we err on preserving user content via the backup path).
        if installed_hash == kit_hash:
            file_statuses[filename] = DeckFileStatus.UP_TO_DATE
        else:
            file_statuses[filename] = DeckFileStatus.LOCALLY_MODIFIED

    return DeckSyncReport(
        kit_version=get_package_version(),
        installed_kit_version=manifest.kit_version if manifest is not None else None,
        manifest_present=manifest is not None,
        files=file_statuses,
    )
