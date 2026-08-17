"""A surface owns a directory, and a file is claimed by the pair (directory, name).

`test_surface_resolution.py` covers the name half of the claim — exact filenames before globs, and
two globs over one file refused by name. This module covers the half a subdirectory adds: the same
name in two directories is two different files, and only the surface that owns the directory it
sits in may claim it.

The specimen is real and it is the reason this exists at all:
`inference/backends/pipelex_gateway.toml` matches the `pipelex-config` tier glob `pipelex_*.toml`
exactly. Before the walk reached subdirectories, depth alone kept it safe. Now that the walk goes
there on purpose, the *directory* is what has to keep it safe — and if it ever stops doing so, the
main configuration's ledger gets replayed over an inference backend definition and rewrites it.
"""

from pathlib import Path

from pipelex.migration.surfaces import SurfaceRegistry
from tests.unit.pipelex.migration.conftest import SurfaceBuilder

BACKENDS = Path("inference") / "backends"


class TestADirectoryIsHalfTheClaim:
    @staticmethod
    def _registry(build_surface: SurfaceBuilder) -> SurfaceRegistry:
        """The shape the real registry has after S7b: a root family and a subdirectory family."""
        return SurfaceRegistry(
            surfaces=[
                build_surface(surface_id="pipelex-config", base_file="pipelex.toml", tier_glob="pipelex_*.toml"),
                build_surface(surface_id="inference-backend", base_file=None, tier_glob="*.toml", subdirectory=BACKENDS),
            ]
        )

    @staticmethod
    def _seed(root: Path) -> None:
        """A configuration directory holding one of everything the claim rule has to separate."""
        (root / "pipelex.toml").write_text("", encoding="utf-8")
        (root / "pipelex_override.toml").write_text("", encoding="utf-8")
        (root / BACKENDS).mkdir(parents=True)
        (root / BACKENDS / "pipelex_gateway.toml").write_text("", encoding="utf-8")
        (root / BACKENDS / "openai.toml").write_text("", encoding="utf-8")
        (root / BACKENDS / "notes.md").write_text("", encoding="utf-8")
        (root / "inference" / "deck").mkdir(parents=True)
        (root / "inference" / "deck" / "x.toml").write_text("", encoding="utf-8")
        (root / "inference" / "backends.toml").write_text("", encoding="utf-8")

    def test_each_file_goes_to_the_surface_that_owns_the_directory_it_sits_in(self, tmp_path: Path, build_surface: SurfaceBuilder) -> None:
        """One assertion for the whole rule, because every line of it is a separate way to get this wrong.

        `pipelex_gateway.toml` is claimed by the backend surface and *not* by the root surface whose
        glob its name matches; `notes.md` falls out by extension; `deck/` is a directory no surface
        owns and is never entered; `inference/backends.toml` sits one level above the directory the
        backend surface owns and is nobody's.
        """
        self._seed(tmp_path)

        claimed = self._registry(build_surface).files_by_surface_in_directory(directory=tmp_path)

        assert [(surface.surface_id, path.relative_to(tmp_path).as_posix()) for surface, path in claimed] == [
            ("pipelex-config", "pipelex.toml"),
            ("pipelex-config", "pipelex_override.toml"),
            ("inference-backend", "inference/backends/openai.toml"),
            ("inference-backend", "inference/backends/pipelex_gateway.toml"),
        ]

    def test_the_same_name_resolves_to_a_different_surface_in_each_directory(self, build_surface: SurfaceBuilder) -> None:
        """The claim is the pair, so the specimen's name alone answers nothing.

        Without the directory in the question, `pipelex_gateway.toml` is a `pipelex_*.toml` match
        and the root surface takes it wherever it lives.
        """
        registry = self._registry(build_surface)

        at_the_root = registry.surface_for_file(subdirectory=Path(), file_name="pipelex_gateway.toml")
        in_the_backends_directory = registry.surface_for_file(subdirectory=BACKENDS, file_name="pipelex_gateway.toml")

        assert at_the_root is not None
        assert at_the_root.surface_id == "pipelex-config"
        assert in_the_backends_directory is not None
        assert in_the_backends_directory.surface_id == "inference-backend"

    def test_a_root_surfaces_glob_does_not_reach_into_a_directory_it_does_not_own(self, build_surface: SurfaceBuilder) -> None:
        """The other direction of the same rule: the backend directory is not the root surface's to claim in."""
        registry = SurfaceRegistry(surfaces=[build_surface(surface_id="pipelex-config", base_file="pipelex.toml", tier_glob="pipelex_*.toml")])

        assert registry.surface_for_file(subdirectory=BACKENDS, file_name="pipelex_gateway.toml") is None
        assert registry.surface_for_file(subdirectory=BACKENDS, file_name="pipelex.toml") is None

    def test_a_subdirectory_that_does_not_exist_is_skipped_rather_than_refused(self, tmp_path: Path, build_surface: SurfaceBuilder) -> None:
        """A machine that has never run an inference backend has no `inference/` at all."""
        (tmp_path / "pipelex.toml").write_text("", encoding="utf-8")

        claimed = self._registry(build_surface).files_by_surface_in_directory(directory=tmp_path)

        assert [path.name for _, path in claimed] == ["pipelex.toml"]
