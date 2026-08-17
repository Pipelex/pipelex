"""Builders shared by the migration engine's unit tests.

Ledgers are built from the models rather than from TOML text on purpose: these tests are about
what a *parsed* ledger does to a document, and the parsing itself has its own module.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from pipelex.migration.ledger import MigrationEntry, MigrationLedger, SurfaceBlock
from pipelex.migration.safety import MigrationSafety
from pipelex.migration.surfaces import DefaultsLayerKind, Surface, SurfaceRegistry
from pipelex.suggested_fix import MigrationOp

EXAMPLE_SURFACE_ID = "example-config"
EXAMPLE_BASE_FILE = "example.toml"
EXAMPLE_TIER_GLOB = "example_*.toml"
CONFIGURATION_ROOT = Path()
"""The subdirectory a surface that lives directly in a configuration directory owns — none."""

EntryBuilder = Callable[..., MigrationEntry]
LedgerBuilder = Callable[..., MigrationLedger]
SurfaceBuilder = Callable[..., Surface]


@pytest.fixture
def build_entry() -> EntryBuilder:
    def _build_entry(
        *,
        to_schema_version: int,
        ops: list[MigrationOp],
        surface_id: str = EXAMPLE_SURFACE_ID,
        safety: MigrationSafety = MigrationSafety.SAFE,
        guidance: str | None = None,
        title: str = "Reshape the example surface",
        description: str = "The example surface changed shape.",
        breaking: bool = True,
        pre_history: bool = False,
        declared_removed_paths: list[str] | None = None,
        declared_narrowed_paths: list[str] | None = None,
    ) -> MigrationEntry:
        return MigrationEntry(
            id=f"{surface_id}@{to_schema_version}",
            to_schema_version=to_schema_version,
            introduced_in="0.46.0",
            breaking=breaking,
            safety=safety,
            title=title,
            description=description,
            guidance=guidance,
            pre_history=pre_history,
            declared_removed_paths=declared_removed_paths or [],
            declared_narrowed_paths=declared_narrowed_paths or [],
            ops=ops,
        )

    return _build_entry


@pytest.fixture
def build_ledger() -> LedgerBuilder:
    def _build_ledger(
        *,
        entries: list[MigrationEntry],
        surface_id: str = EXAMPLE_SURFACE_ID,
        base_file: str = EXAMPLE_BASE_FILE,
        tier_glob: str | None = EXAMPLE_TIER_GLOB,
        min_supported_schema_version: int = 0,
    ) -> MigrationLedger:
        return MigrationLedger(
            surface=SurfaceBlock(
                id=surface_id,
                title="An example configuration surface",
                base_file=base_file,
                tier_glob=tier_glob,
                current_schema_version=1 + len(entries),
                min_supported_schema_version=min_supported_schema_version,
            ),
            migration=entries,
        )

    return _build_ledger


class ExampleOutput(BaseModel):
    directory: str = "out"


class ExampleReporting(BaseModel):
    output: ExampleOutput = Field(default_factory=ExampleOutput)
    destination: str | None = None


class ExampleConfig(BaseModel):
    """A stand-in configuration model for surfaces the tests invent.

    It has to name the paths the fixtures' *migrated* documents carry, and not only the ones a test
    happens to assert on. A migration run diagnoses what it leaves behind against this model, so a
    path missing here is reported as unexplained — which is the diagnosis working, and noise in
    every test that was about something else.
    """

    label: str = "hello"
    reporting: ExampleReporting = Field(default_factory=ExampleReporting)


@pytest.fixture
def build_surface() -> SurfaceBuilder:
    def _build_surface(
        *,
        surface_id: str = EXAMPLE_SURFACE_ID,
        base_file: str | None = EXAMPLE_BASE_FILE,
        tier_glob: str | None = EXAMPLE_TIER_GLOB,
        subdirectory: Path = CONFIGURATION_ROOT,
    ) -> Surface:
        return Surface(
            surface_id=surface_id,
            title=surface_id,
            base_file=base_file,
            tier_glob=tier_glob,
            subdirectory=subdirectory,
            config_model=ExampleConfig,
            defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
        )

    return _build_surface


@pytest.fixture
def write_ledger_file() -> Callable[..., Path]:
    """Write a minimal ledger TOML into a temporary migration directory."""

    def _write_ledger_file(*, migration_dir: Path, surface_id: str, body: str) -> Path:
        ledgers = migration_dir / "ledgers"
        ledgers.mkdir(parents=True, exist_ok=True)
        path = ledgers / f"{surface_id}.toml"
        path.write_text(body, encoding="utf-8")
        return path

    return _write_ledger_file


@pytest.fixture
def build_registry(build_surface: SurfaceBuilder) -> Callable[..., SurfaceRegistry]:
    def _build_registry(*, surfaces: list[Surface] | None = None) -> SurfaceRegistry:
        return SurfaceRegistry(surfaces=surfaces or [build_surface()])

    return _build_registry
