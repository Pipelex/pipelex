"""Model deck manifest: detect when an installed deck has drifted from the kit-shipped templates.

The manifest pins, for one specific deck install, the kit version that produced it and the SHA-256 of
each managed deck file at install/update time. It enables three independent signals:

- Manifest's ``kit_version`` vs the running ``pipelex`` version → behind upstream.
- Manifest's per-file hash vs the installed file's actual hash → user has locally edited a numbered file.
- Kit content vs installed content → upstream changed.

Numbered deck files (``1_llm_deck.toml``...``4_search_deck.toml``) are pipelex-managed.
``x_custom_*.toml`` files are user-owned and never tracked.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.types import StrEnum

MANIFEST_FILENAME = ".kit_manifest.json"


class DeckFileStatus(StrEnum):
    """Per-file sync status between the installed deck and the kit-shipped templates."""

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
    """Result of comparing an installed deck dir to the currently shipping kit."""

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


def _is_managed_deck_filename(filename: str) -> bool:
    """True for files that pipelex manages (numbered ``*_deck.toml``).

    Excludes any ``x_custom_*.toml`` override (the user-owned escape hatch) and non-TOML files
    (e.g. an accidental ``.DS_Store``). The ``x_custom_`` prefix is the agreed-upon namespace for
    user overrides — pipelex never tracks or overwrites those.
    """
    if not filename.endswith(".toml"):
        return False
    return not filename.startswith("x_custom_")


def list_managed_kit_files() -> dict[str, str]:
    """Hash every managed deck file shipped in the current pipelex wheel."""
    kit_dir = kit_deck_dir()
    return {
        entry.name: compute_file_sha256(entry) for entry in sorted(kit_dir.iterdir()) if entry.is_file() and _is_managed_deck_filename(entry.name)
    }


def list_managed_installed_files(deck_dir: Path) -> dict[str, str]:
    """Hash every managed deck file present in the user's installed deck dir."""
    if not deck_dir.is_dir():
        return {}
    return {
        entry.name: compute_file_sha256(entry) for entry in sorted(deck_dir.iterdir()) if entry.is_file() and _is_managed_deck_filename(entry.name)
    }


def compute_kit_manifest() -> DeckManifest:
    """Build the manifest that should be written after a fresh install or successful update."""
    return DeckManifest(kit_version=get_package_version(), files=list_managed_kit_files())


def manifest_path(deck_dir: Path) -> Path:
    return deck_dir / MANIFEST_FILENAME


def read_manifest(deck_dir: Path) -> DeckManifest | None:
    """Return the persisted manifest, or ``None`` when absent or unreadable.

    A corrupt manifest is treated as missing — the caller will warn the user and offer to rebuild it.
    """
    target = manifest_path(deck_dir)
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


def write_manifest(deck_dir: Path, manifest: DeckManifest) -> None:
    """Persist the manifest, creating the deck directory if needed."""
    deck_dir.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump()
    target = manifest_path(deck_dir)
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
    return _is_manifest_older(manifest.kit_version, get_package_version())


def _is_manifest_older(manifest_version: str, current_version: str) -> bool:
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


def compute_deck_sync_report(deck_dir: Path) -> DeckSyncReport:
    """Full per-file diff between the installed deck and the running pipelex's kit.

    This walks every managed file in either side and assigns it a ``DeckFileStatus``. Cost is one
    SHA-256 per file — only call from ``pipelex update`` and ``pipelex doctor``, never on the boot path.
    """
    kit_files = list_managed_kit_files()
    installed_files = list_managed_installed_files(deck_dir)
    manifest = read_manifest(deck_dir)
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
