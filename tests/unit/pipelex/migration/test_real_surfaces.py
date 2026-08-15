"""The one test that points the gate at the real configuration surfaces.

Everything else about gate behaviour is tested against synthetic models, deliberately. What is
left for this module is the question those tests cannot answer: does the apparatus actually load
*our* models, *our* ledgers and *our* goldens, and do they agree today?

That question is worth exactly this much coverage. Assert more here — the number of paths, a
specific key, a particular default — and every legitimate configuration change goes red in a test
that is not about configuration, which teaches the reflex the whole design exists to prevent.
"""

from pipelex.migration.coverage import check_registry
from pipelex.migration.ledger import INITIAL_SCHEMA_VERSION, load_ledger
from pipelex.migration.surfaces import build_config_surface_registry, packaged_migration_dir


class TestTheRealRegistry:
    def test_the_registry_loads(self) -> None:
        registry = build_config_surface_registry()
        assert [surface.surface_id for surface in registry.surfaces] == [
            "pipelex-config",
            "telemetry-config",
            "pipelex-service-config",
        ]

    def test_every_surface_has_a_reachable_defaults_layer(self) -> None:
        """The premise the whole vocabulary rests on: without it, an added key breaks every file."""
        for surface in build_config_surface_registry().surfaces:
            assert surface.read_defaults_document(), f"surface '{surface.surface_id}' supplies no defaults"

    def test_every_surface_has_a_ledger(self) -> None:
        migration_dir = packaged_migration_dir()
        for surface in build_config_surface_registry().surfaces:
            ledger = load_ledger(migration_dir=migration_dir, surface_id=surface.surface_id)
            assert ledger.surface.id == surface.surface_id
            assert ledger.surface.current_schema_version >= INITIAL_SCHEMA_VERSION


class TestTheCheckedInGoldens:
    def test_the_real_surfaces_pass_the_coverage_check(self) -> None:
        """The checked-in goldens match today's models.

        When this fails, it is not this test that is wrong: a configuration model moved, and the
        gate is telling you to either regenerate the golden (`make umig`) or record the migration
        that repairs the files the change broke.
        """
        issues = check_registry(registry=build_config_surface_registry(), migration_dir=packaged_migration_dir())
        assert issues == [], "\n".join(f"{issue.surface_id}: {issue.message}" for issue in issues)
