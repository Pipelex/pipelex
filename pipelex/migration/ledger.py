"""The ledger — the checked-in record of every shape change a surface has undergone.

**A ledger is data and never code.** The checks must reason mechanically about what every entry
does — which paths it removes, which values it remaps, whether replay converges — and executable
steps defeat every one of those checks.

The models below are strict on purpose. An entry whose id disagrees with its version, or a ledger
whose versions skip a number, is refused when the file is parsed rather than diagnosed later by a
gate: the earlier a malformed ledger stops, the fewer places have to cope with one.

See `docs/migration-ledger.md` → "The ledger file".
"""

from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing_extensions import Self

from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.suggested_fix import MigrationOp
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_path

LEDGERS_DIR_NAME = "ledgers"
INITIAL_SCHEMA_VERSION = 1
"""Every surface starts here. There is no retroactive numbering of changes that predate the ledger."""


class MigrationSafety(StrEnum):
    """Whether the applier may act on an entry.

    Independent of `guidance`, which any entry may carry whatever its safety.
    """

    SAFE = "safe"
    """Mechanically complete; applied after one confirmation."""

    UNSAFE = "unsafe"
    """Reported and never applied — the applier cannot tell a stale value from a deliberate one."""


class SurfaceBlock(BaseModel):
    """The `[surface]` block: what the ledger claims about the surface it governs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    base_file: str
    tier_glob: str | None = None
    current_schema_version: int = Field(ge=INITIAL_SCHEMA_VERSION)
    min_supported_schema_version: int = Field(ge=0)
    """Held at zero until a ledger squash ever moves it. Without the floor, a squash silently
    under-migrates the oldest files in the field, because the applier skips absent targets and
    reports success. With it, the loader fails loudly instead."""

    @model_validator(mode="after")
    def check_floor_is_below_the_current_version(self) -> Self:
        if self.min_supported_schema_version > self.current_schema_version:
            msg = (
                f"surface '{self.id}': min_supported_schema_version {self.min_supported_schema_version} "
                f"is above current_schema_version {self.current_schema_version}"
            )
            raise ValueError(msg)
        return self


class MigrationEntry(BaseModel):
    """One schema version's worth of change, as data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    to_schema_version: int = Field(gt=INITIAL_SCHEMA_VERSION)
    """Above 1: version 1 is the shape a surface starts at, so nothing migrates *to* it."""

    introduced_in: str
    """The package version carrying this entry. Orientation against the changelog only —
    nothing branches on it."""

    breaking: bool
    safety: MigrationSafety = Field(strict=False)
    title: str
    description: str
    guidance: str | None = None
    """Agent-facing Markdown: what a user should understand or decide. Never the mechanism —
    anything expressible as operations must be operations."""

    pre_history: bool = False
    """A removal that predates the first fingerprint has no observed diff to account against, so
    such an entry declares its own removed paths instead."""

    declared_removed_paths: list[str] = Field(default_factory=list[str])
    ops: list[MigrationOp] = Field(default_factory=list[MigrationOp])
    """May legitimately be empty, with `safety = "unsafe"`, for a change only a human can make."""

    @model_validator(mode="after")
    def check_declared_removals_belong_to_pre_history(self) -> Self:
        if self.declared_removed_paths and not self.pre_history:
            msg = (
                f"entry '{self.id}': declared_removed_paths is for pre-history entries only — an entry with an "
                f"observable fingerprint diff is accounted against that diff, not against its own declaration"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_pre_history_declares_what_it_removed(self) -> Self:
        if self.pre_history and not self.declared_removed_paths:
            msg = (
                f"entry '{self.id}': a pre-history entry declares the paths it removes — the flag exempts the entry from "
                f"being accounted against a fingerprint diff, and the declaration is what replaces that diff, so an entry "
                f"carrying the flag and declaring nothing is exempt from every accounting there is"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_an_op_free_entry_is_unsafe(self) -> Self:
        if not self.ops and self.safety is MigrationSafety.SAFE:
            msg = f"entry '{self.id}': an entry with no operations cannot be 'safe' — there is nothing for the applier to do"
            raise ValueError(msg)
        return self


class MigrationLedger(BaseModel):
    """One surface's whole ledger, as parsed from its checked-in TOML file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface: SurfaceBlock
    migration: list[MigrationEntry] = Field(default_factory=list[MigrationEntry])

    @model_validator(mode="after")
    def check_entries_are_contiguous_and_named_for_their_version(self) -> Self:
        expected_version = INITIAL_SCHEMA_VERSION
        for entry in self.migration:
            expected_version += 1
            if entry.to_schema_version != expected_version:
                msg = (
                    f"ledger '{self.surface.id}': entries must be ordered and contiguous — expected an entry for "
                    f"schema version {expected_version}, found '{entry.id}' at {entry.to_schema_version}"
                )
                raise ValueError(msg)
            expected_id = f"{self.surface.id}@{entry.to_schema_version}"
            if entry.id != expected_id:
                msg = f"ledger '{self.surface.id}': entry at schema version {entry.to_schema_version} must be named '{expected_id}', not '{entry.id}'"
                raise ValueError(msg)
        if expected_version != self.surface.current_schema_version:
            msg = (
                f"ledger '{self.surface.id}': current_schema_version is {self.surface.current_schema_version} but the entries "
                f"reach {expected_version} — every version above {INITIAL_SCHEMA_VERSION} needs the entry that produced it"
            )
            raise ValueError(msg)
        return self

    def entry_for_version(self, *, schema_version: int) -> MigrationEntry | None:
        for entry in self.migration:
            if entry.to_schema_version == schema_version:
                return entry
        return None


def ledgers_dir(*, migration_dir: Path) -> Path:
    return migration_dir / LEDGERS_DIR_NAME


def ledger_path(*, migration_dir: Path, surface_id: str) -> Path:
    return ledgers_dir(migration_dir=migration_dir) / f"{surface_id}.toml"


def load_ledger(*, migration_dir: Path, surface_id: str) -> MigrationLedger:
    """Read and validate one surface's ledger.

    Raises:
        MigrationLedgerError: the file is missing, unparseable, or internally inconsistent.
    """
    path = ledger_path(migration_dir=migration_dir, surface_id=surface_id)
    try:
        raw: dict[str, Any] = load_toml_from_path(path=path)
    except FileNotFoundError as exc:
        msg = f"no ledger for surface '{surface_id}' at {path}"
        raise MigrationLedgerError(msg) from exc
    except TomlError as exc:
        msg = f"unparseable ledger for surface '{surface_id}' at {path}: {exc}"
        raise MigrationLedgerError(msg) from exc
    try:
        return MigrationLedger.model_validate(raw)
    except ValidationError as exc:
        msg = f"invalid ledger for surface '{surface_id}' at {path}: {exc}"
        raise MigrationLedgerError(msg) from exc


@cache
def load_ledger_cached(*, migration_dir: Path, surface_id: str) -> MigrationLedger:
    """`load_ledger`, parsed once per process.

    Replaying a surface over a directory of files must not re-parse the same TOML per file: the
    ledger is checked-in package data that cannot change under a running process, and the parsed
    model is frozen. Use this everywhere that reads a ledger during a run; `load_ledger` itself
    stays uncached for the gates, which are told which directory to read and are asked to see
    what is on disk right now.

    A raise is not cached — `lru_cache` only records successful calls — so a ledger fixed on disk
    between two calls is re-read rather than failing forever.
    """
    return load_ledger(migration_dir=migration_dir, surface_id=surface_id)
