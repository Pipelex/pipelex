"""The one test that points the gate at the real configuration surfaces.

Everything else about gate behaviour is tested against synthetic models, deliberately. What is
left for this module is the question those tests cannot answer: does the apparatus actually load
*our* models, *our* ledgers and *our* goldens, and do they agree today?

That question is worth exactly this much coverage. Assert more here — the number of paths, a
specific key, a particular default — and every legitimate configuration change goes red in a test
that is not about configuration, which teaches the reflex the whole design exists to prevent.
"""

import tomlkit

from pipelex.migration.coverage import check_defaults_layer, check_registry
from pipelex.migration.diagnosis import diagnose_unexplained_paths
from pipelex.migration.ledger import INITIAL_SCHEMA_VERSION, load_ledger, packaged_migration_dir
from pipelex.migration.ledger_check import check_ledgers
from pipelex.migration.surfaces import build_config_surface_registry
from pipelex.migration.transform_check import check_transforms


class TestTheRealRegistry:
    def test_the_registry_loads(self) -> None:
        registry = build_config_surface_registry()
        assert [surface.surface_id for surface in registry.surfaces] == [
            "pipelex-config",
            "telemetry-config",
            "pipelex-service-config",
            "inference-backend",
        ]

    def test_every_surface_has_a_reachable_defaults_layer(self) -> None:
        """The premise the whole vocabulary rests on: without it, an added key breaks every file.

        Stated per kind rather than as "the defaults document is non-empty", which was a proxy that
        held only while every surface had one. A **copied**-document surface honestly has none — its
        files stand alone, nothing is merged beneath them — and its half of the premise is that the
        rule holds anyway, because no path of such a file is one a defaults layer would have to supply.
        That is what `check_defaults_layer` decides, and it is asked here rather than assumed: a
        document faked to satisfy a truthiness check would attribute one backend file's values to
        every other one.
        """
        for surface in build_config_surface_registry().surfaces:
            if surface.defaults_layer_kind.is_layered_beneath_the_users_file:
                assert surface.read_defaults_document(), f"surface '{surface.surface_id}' supplies no defaults"
                continue
            assert surface.read_defaults_document() == {}, f"surface '{surface.surface_id}' fakes a defaults document"
            issues = check_defaults_layer(surface_id=surface.surface_id, fingerprint=surface.fingerprint_at(schema_version=1))
            assert issues == [], f"surface '{surface.surface_id}': {[issue.message for issue in issues]}"

    def test_a_surface_whose_documents_root_keys_are_the_users_records_an_open_root(self) -> None:
        """The shape the whole fourth surface rests on, asserted once against the real registry.

        `*` and every path beneath it, and no path above it: a fingerprint that recorded `sdk` at the
        top would be describing a document nobody has, and every operation written against it would
        be dead on every file in the field.
        """
        for surface in build_config_surface_registry().surfaces:
            if not surface.document_shape.document_root_is_open:
                continue
            fingerprint = surface.fingerprint_at(schema_version=1)
            assert fingerprint.document_root_is_open is True
            assert all(path == "*" or path.startswith("*.") for path in fingerprint.paths)

    def test_no_surfaces_own_documents_carry_anything_the_diagnosis_cannot_explain(self) -> None:
        """The downgrade diagnosis, over the two documents it must always be silent about.

        Both are at the current schema by construction — one is the defaults layer, the other the
        starter file `pipelex init` copies — so a path it cannot account for in either is the
        diagnosis being wrong about our own schema, not the document being stale.
        """
        migration_dir = packaged_migration_dir()
        for surface in build_config_surface_registry().surfaces:
            ledger = load_ledger(migration_dir=migration_dir, surface_id=surface.surface_id)
            fingerprint = surface.fingerprint_at(schema_version=ledger.surface.current_schema_version)
            for label, text in surface.reference_documents():
                unexplained = diagnose_unexplained_paths(
                    surface=surface,
                    fingerprint=fingerprint,
                    document=tomlkit.loads(text).unwrap(),
                    ledger=ledger,
                    blocked=[],
                )
                assert unexplained == [], f"{surface.surface_id} ({label}): {[found.path for found in unexplained]}"

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

    def test_the_real_ledgers_pass_the_ledger_check(self) -> None:
        """The checked-in ledgers say only legal things, and replay over our own documents does nothing.

        The convergence half of this is the one assertion here that is not about the goldens at
        all: it replays every ledger over the packaged configuration and the kit template, which
        is exactly what a user's machine will do to their own file.
        """
        ledger_issues = check_ledgers(registry=build_config_surface_registry(), migration_dir=packaged_migration_dir())
        assert ledger_issues == [], "\n".join(f"{issue.surface_id}: {issue.message}" for issue in ledger_issues)

    def test_the_real_transform_chains_hold(self) -> None:
        """Every entry, applied to the document of the version before it, lands on the next one.

        No longer vacuous: `telemetry-config@2` is a pre-history entry, so this walks its
        hand-authored `before@2.toml` through its operations and holds the result against today's
        shape and today's model.
        """
        transform_issues = check_transforms(registry=build_config_surface_registry(), migration_dir=packaged_migration_dir())
        assert transform_issues == [], "\n".join(f"{issue.surface_id}: {issue.message}" for issue in transform_issues)
