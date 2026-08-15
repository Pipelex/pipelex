"""Unit tests for resolving which surface owns a file.

Which ledger runs over a file must never be an accident of iteration order. The registry refuses
what it can decide by name alone when it loads; what it cannot decide — whether two glob languages
overlap — is decided here, where there is a real file to point at.
"""

import re
from pathlib import Path

import pytest

from pipelex.migration.exceptions import MigrationRegistryError
from pipelex.migration.surfaces import SurfaceRegistry
from tests.unit.pipelex.migration.conftest import SurfaceBuilder


class TestSurfaceResolution:
    def test_an_exact_base_file_claims_before_another_surfaces_glob(self, build_surface: SurfaceBuilder) -> None:
        """The real configuration: `pipelex_service.toml` also matches `pipelex_*.toml`."""
        registry = SurfaceRegistry(
            surfaces=[
                build_surface(surface_id="pipelex-config", base_file="pipelex.toml", tier_glob="pipelex_*.toml"),
                build_surface(surface_id="pipelex-service-config", base_file="pipelex_service.toml", tier_glob=None),
            ]
        )

        resolved = registry.surface_for_file_name(file_name="pipelex_service.toml")

        assert resolved is not None
        assert resolved.surface_id == "pipelex-service-config"

    def test_a_tier_file_resolves_to_the_surface_whose_glob_matches(self, build_surface: SurfaceBuilder) -> None:
        registry = SurfaceRegistry(surfaces=[build_surface(surface_id="pipelex-config", base_file="pipelex.toml", tier_glob="pipelex_*.toml")])

        resolved = registry.surface_for_file_name(file_name="pipelex_staging.toml")

        assert resolved is not None
        assert resolved.surface_id == "pipelex-config"

    def test_a_file_no_surface_claims_resolves_to_nothing(self, build_surface: SurfaceBuilder) -> None:
        registry = SurfaceRegistry(surfaces=[build_surface(surface_id="pipelex-config", base_file="pipelex.toml", tier_glob="pipelex_*.toml")])

        assert registry.surface_for_file_name(file_name="plxt.toml") is None

    def test_a_file_two_globs_both_claim_stops_by_name(self, build_surface: SurfaceBuilder) -> None:
        """The registry accepts these globs — deciding overlap between glob *languages* is not its
        job, and it has no files to look at. Here there is one, and it is refused with its name.

        Today's registry has one glob per family and none overlap, so nothing else would catch a
        future one.
        """
        registry = SurfaceRegistry(
            surfaces=[
                build_surface(surface_id="a", base_file="a.toml", tier_glob="pipelex_*.toml"),
                build_surface(surface_id="b", base_file="b.toml", tier_glob="*_local.toml"),
            ]
        )

        with pytest.raises(MigrationRegistryError, match=re.escape("pipelex_local.toml")):
            registry.surface_for_file_name(file_name="pipelex_local.toml")

    def test_a_directory_walk_returns_the_claimed_files_with_their_surfaces(
        self,
        tmp_path: Path,
        build_surface: SurfaceBuilder,
    ) -> None:
        registry = SurfaceRegistry(surfaces=[build_surface(surface_id="example-config", base_file="example.toml", tier_glob="example_*.toml")])
        (tmp_path / "example.toml").write_text("", encoding="utf-8")
        (tmp_path / "example_local.toml").write_text("", encoding="utf-8")
        (tmp_path / "unrelated.toml").write_text("", encoding="utf-8")
        (tmp_path / "example_dir.toml").mkdir()

        claimed = registry.files_by_surface_in_directory(directory=tmp_path)

        assert [path.name for _, path in claimed] == ["example.toml", "example_local.toml"]

    def test_a_missing_directory_is_skipped_rather_than_refused(self, tmp_path: Path, build_surface: SurfaceBuilder) -> None:
        """A machine with only a global configuration directory is an ordinary machine."""
        registry = SurfaceRegistry(surfaces=[build_surface()])

        assert registry.files_by_surface_in_directory(directory=tmp_path / "nowhere") == []
