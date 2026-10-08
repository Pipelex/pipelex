"""The doctor on a machine a former release set up: the migrations row names the cleanup, and the models row defers to it.

The migrations row is `pipelex migrate`'s own dry run, and that command's first step is the cleanup of what a release
that ran on the Pipelex Gateway or Pipelex Manifold left, so the row reports it with the files it is about. The models
row would otherwise meet the refusal a boot meets on such a machine, about one backend or one profile; it names the
cleanup instead.

The home is the v0.72 kit, copied from that release's wheel. Whether what it left stops the boot is read off the files
the boot itself merges, across the home and the project, so a project that boots on a base of its own is not told it
cannot start, and a profile one directory activates from the other is not missed.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.doctor_cmd import _pending_migrations_actions  # pyright: ignore[reportPrivateUsage]
from pipelex.cli.commands import doctor_cmd as doctor_cmd_module
from pipelex.cli.commands.doctor_cmd import PendingMigrationsFinding, check_backend_credentials, check_models, check_pending_migrations
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.kit.paths import RETIRED_SERVICE_FILE_NAME, get_kit_configs_dir
from pipelex.migration.former_release import RETIRED_BACKEND_NAMES
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, ROUTING_PROFILES_FILE_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

pytestmark = pytest.mark.usefixtures("no_pipelex_home")

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")

# The files the cleanup touches in the v0.72 directory, in the order it reports them.
V0_72_CLEANUP_FILES = [
    f"{INFERENCE_DIR_NAME}/{BACKENDS_FILE_NAME}",
    f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}/pipelex_gateway.toml",
    f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}/pipelex_manifold.toml",
    f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}/pipelex_gateway_models.md",
    f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}/pipelex_gateway_models_plain.md",
    RETIRED_SERVICE_FILE_NAME,
    f"{INFERENCE_DIR_NAME}/{ROUTING_PROFILES_FILE_NAME}",
]

# A model table whose key the inference-backend ledger renames.
MIGRATABLE_MODEL_TABLE = '\n["gpt-4o"]\nprompting_target = "openai"\n'


@pytest.fixture
def machine(tmp_path: Path, mocker: MockerFixture) -> tuple[Path, Path]:
    """A fake home and a project, both configuration directories still to be written: the home's and the project's."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)
    return fake_home / ".pipelex", project_root / ".pipelex"


@pytest.fixture
def former_release_home(machine: tuple[Path, Path]) -> Path:
    """A fake home holding the v0.72 kit, and a project without a `.pipelex/`, so the walk reads this test's files."""
    config_dir, _ = machine
    shutil.copytree(V0_72_CONFIG_DIR, config_dir)
    return config_dir


def _snapshot(*, directory: Path) -> dict[str, bytes]:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


class TestTheDoctorOnAFormerRelease:
    def test_the_migrations_row_names_what_a_former_release_left_and_that_it_stops_the_boot(self, former_release_home: Path) -> None:
        check = check_pending_migrations()

        assert check.finding == PendingMigrationsFinding.PENDING
        assert check.finding.is_repaired_by_migrating
        assert check.migratable_files == []
        assert check.former_release_files == [str(former_release_home / relative_path) for relative_path in V0_72_CLEANUP_FILES]
        assert check.former_release_blocks_boot
        assert "former release" in check.message
        assert f"'{MIGRATE_COMMAND}'" in check.message
        assert "cannot start" in check.message

    def test_the_row_is_a_dry_run_and_writes_nothing(self, former_release_home: Path) -> None:
        before = _snapshot(directory=former_release_home)

        check_pending_migrations()

        assert _snapshot(directory=former_release_home) == before

    def test_the_models_row_names_the_cleanup_rather_than_a_refusal_about_one_backend(self, former_release_home: Path) -> None:
        healthy, message, backend_file_reports = check_models(secrets_provider=EnvSecretsProvider(), config_dir=former_release_home)

        assert not healthy
        assert backend_file_reports == {}
        assert f"'{MIGRATE_COMMAND}'" in message
        assert "former release" in message

    def test_the_credentials_row_never_asks_for_a_retired_backends_key(self, former_release_home: Path) -> None:
        """Setting the Gateway's key is no remedy: the backend is gone, and the migrations row names the cleanup."""
        _, backend_reports, _ = check_backend_credentials(config_dir=former_release_home)

        assert backend_reports, "the other enabled backends are still checked"
        assert not set(backend_reports) & RETIRED_BACKEND_NAMES

    @pytest.mark.usefixtures("former_release_home")
    def test_a_project_booting_on_a_base_of_its_own_is_not_told_it_cannot_start(self, machine: tuple[Path, Path]) -> None:
        """The common case: a v0.72 home, and a project set up since, whose own base files are the ones the boot reads."""
        _, project_config_dir = machine
        shutil.copytree(Path(str(get_kit_configs_dir())), project_config_dir)

        check = check_pending_migrations()

        assert check.former_release_files, "the home still carries what the release left, and the row lists it"
        assert not check.former_release_blocks_boot
        assert "cannot start" not in check.message

    def test_a_retired_profile_activated_from_the_other_directory_stops_the_boot(self, machine: tuple[Path, Path]) -> None:
        """Each directory alone boots; merged as the boot merges them, the home's override activates the project's retired profile."""
        home_config_dir, project_config_dir = machine
        kit_inference = Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME
        for config_dir in (home_config_dir, project_config_dir):
            shutil.copytree(kit_inference, config_dir / INFERENCE_DIR_NAME)
        (home_config_dir / INFERENCE_DIR_NAME / "routing_profiles_override.toml").write_text('active = "my_gw"\n', encoding="utf-8")
        with (project_config_dir / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME).open("a", encoding="utf-8") as stream:
            stream.write('\n[profiles.my_gw]\ndescription = "mine"\ndefault = "pipelex_gateway"\n')

        check = check_pending_migrations()

        assert check.former_release_blocks_boot
        assert "cannot start" in check.message

    @pytest.mark.usefixtures("former_release_home")
    def test_a_failure_reading_what_the_boot_reads_leaves_the_row_unchecked(self, mocker: MockerFixture) -> None:
        mocker.patch.object(doctor_cmd_module, "former_release_boot_blockers", side_effect=PermissionError(13, "Permission denied"))

        check = check_pending_migrations()

        assert check.finding == PendingMigrationsFinding.UNAVAILABLE

    def test_a_file_the_cleanup_removes_is_not_offered_for_migration(self, former_release_home: Path) -> None:
        gateway_file = former_release_home / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "pipelex_gateway.toml"
        with gateway_file.open("a", encoding="utf-8") as stream:
            stream.write(MIGRATABLE_MODEL_TABLE)

        check = check_pending_migrations()

        assert str(gateway_file) in check.former_release_files
        assert str(gateway_file) not in check.migratable_files

    def test_a_catch_all_route_to_the_gateway_is_offered_for_cleanup_rather_than_crashing_the_row(self, machine: tuple[Path, Path]) -> None:
        home, _ = machine
        shutil.copytree(Path(str(get_kit_configs_dir())), home)
        routing_path = home / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME
        routing_path.write_text(
            'active = "mine"\n\n[profiles.mine]\ndescription = "everything through the gateway except claude"\ndefault = "openai"\n\n'
            '[profiles.mine.routes]\n"*" = "pipelex_gateway"\n"claude-*" = "anthropic"\n',
            encoding="utf-8",
        )

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.PENDING
        assert check.former_release_files == [str(routing_path)]
        assert check.former_release_blocks_boot

    def test_a_boot_still_stopped_with_nothing_left_to_clean_needs_attention(self, machine: tuple[Path, Path]) -> None:
        """What a cleanup run from another project leaves: no file a former release left, and an `active` naming a profile it removed."""
        home, project = machine
        shutil.copytree(Path(str(get_kit_configs_dir())), home)
        project_override = project / INFERENCE_DIR_NAME / "routing_profiles_override.toml"
        project_override.parent.mkdir(parents=True)
        project_override.write_text('active = "team_gateway"\n', encoding="utf-8")

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.NEEDS_ATTENTION
        assert check.former_release_files == []
        assert f"Pipelex would still not start once '{MIGRATE_COMMAND}' has run" in check.message

    def test_a_home_override_activating_a_profile_no_file_defines_names_the_dry_run_as_its_remedy(self, machine: tuple[Path, Path]) -> None:
        """Nothing is left to clean and `--fix` has nothing to write, so the dry run, which says what stops the boot, is the one move left."""
        home, _ = machine
        shutil.copytree(Path(str(get_kit_configs_dir())), home)
        (home / INFERENCE_DIR_NAME / "routing_profiles_override.toml").write_text('active = "team_gateway"\n', encoding="utf-8")

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.NEEDS_ATTENTION
        assert not check.finding.is_repaired_by_migrating
        assert (check.former_release_files, check.migratable_files, check.attention_files) == ([], [], [])
        actions = _pending_migrations_actions(check=check)
        assert any(action.startswith(f"Run '{MIGRATE_COMMAND} --dry-run' to see what still stops Pipelex from starting") for action in actions)
        assert check.boot_still_blocked
