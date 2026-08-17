"""A fresh machine's backend directory, put on the real walk.

Every other test of this surface holds one half of it still. `test_surface_directories.py` proves the
claim rule over a synthetic registry and hand-written file names; `test_real_surfaces.py` proves the
shipped ledger is neutral over the kit's backend documents by replaying it over their *text*, in
memory, inside the gate. Neither one is what a user meets, and the gap between them is where a defect
of this surface would live: a real directory of real backend files, resolved by the real registry,
replayed by the real run, and diagnosed against the real fingerprint.

The directory is the one `pipelex init` copies, so it is at the current schema by construction and is
nobody's fixture to keep up to date — the same reason the gate uses it as a witness. What this module
adds is that the walk *reaches* it and the run leaves it alone.
"""

import shutil
from pathlib import Path

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.run import migrate_config_directories
from pipelex.migration.surfaces import build_config_surface_registry
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, INFERENCE_DIR_NAME
from pipelex.system.configuration.config_surface import INFERENCE_BACKEND_CONFIG_SURFACE_ID


class TestAFreshMachinesBackendDirectory:
    @staticmethod
    def _seed(*, root: Path) -> list[Path]:
        """Copy the kit's backend directory into a configuration root, and say what landed there.

        Copied rather than pointed at: the walk claims files inside a *configuration* directory, and
        the kit's own copy of them is a package resource. `pipelex init` copies every `.toml` and
        `.md` of it, so every file is copied here — a file the kit ships and the walk then has an
        opinion about is exactly what this module is for.
        """
        kit_backends = Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME
        target = root / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME
        target.mkdir(parents=True)
        for kit_file in sorted(kit_backends.iterdir()):
            shutil.copy2(kit_file, target / kit_file.name)
        return sorted(target.iterdir())

    def test_every_backend_definition_is_claimed_and_the_documentation_beside_them_is_not(self, tmp_path: Path) -> None:
        """The claim rule over the real registry and a real directory listing, not a synthetic one.

        The `.md` files are the half that only a real directory can prove: they are there because the
        kit ships them next to the backends it documents, and a surface claiming `*.toml` leaves them
        alone by extension rather than by an exclusion anybody has to maintain.
        """
        seeded = self._seed(root=tmp_path)
        assert [path.name for path in seeded if path.suffix == ".md"], "worthless unless the kit still ships documentation in there"

        claimed = build_config_surface_registry().files_by_surface_in_directory(directory=tmp_path)

        assert {surface.surface_id for surface, _ in claimed} == {INFERENCE_BACKEND_CONFIG_SURFACE_ID}
        assert [path for _, path in claimed] == [path for path in seeded if path.suffix == ".toml"]

    def test_a_dry_run_over_it_finds_every_file_and_reports_them_all_clean(self, tmp_path: Path) -> None:
        """Convergence proved on the walk: the shipped ledger has nothing to do to a current file.

        Both halves are load-bearing. That the run *finds* every backend definition is the walk; that
        it reports each one clean is the property — nothing applied, nothing blocked, and nothing the
        current schema cannot explain. The last one is new here rather than a restatement of the
        gate's convergence check: that check compares text before and after a replay, and never asks
        the diagnosis anything. A Portkey backend is full of `x-portkey-*` request headers, so a
        surface that did not admit them by shape would pass every gate and then greet a fresh machine
        with a page of unexplained paths.
        """
        seeded = self._seed(root=tmp_path)

        report = migrate_config_directories(config_dirs=[tmp_path], dry_run=True)

        assert [plan.file_path for plan in report.plans] == [path for path in seeded if path.suffix == ".toml"]
        assert [(plan.file_path.name, found.path) for plan in report.plans for found in plan.unexplained] == []
        assert report.is_clean

    def test_a_misspelled_setting_in_one_of_them_is_named_by_the_walk(self, tmp_path: Path) -> None:
        """Without this, the test above would pass just as well over a run that diagnoses nothing.

        A misspelling rather than one of the genuinely dead keys this surface exists to retire: a
        dead key earns a ledger entry that explains it, and a test asserting it is *unexplained*
        would have to be rewritten the day that entry lands. A typo no ledger will ever carry keeps
        saying the same thing.

        It is reported as the schema spells it — `*.<key>`, not `<model>.<key>` — because the model
        name is the user's own and every backend file has different ones.
        """
        self._seed(root=tmp_path)
        target = tmp_path / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "openai.toml"
        target.write_text(f"{target.read_text(encoding='utf-8')}\n[witness-model]\nmaxx_tokens = 8\n", encoding="utf-8")

        report = migrate_config_directories(config_dirs=[tmp_path], dry_run=True)

        assert [(plan.file_path.name, found.path) for plan in report.plans for found in plan.unexplained] == [("openai.toml", "*.maxx_tokens")]
