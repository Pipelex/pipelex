"""The doctor on a machine a former release set up: the migrations row names the cleanup, and the models row defers to it.

The migrations row is `pipelex migrate`'s own dry run, and that command's first step is the cleanup of what a release
that ran on the Pipelex Gateway or Pipelex Manifold left, so the row reports it with the files it is about. The models
row would otherwise meet the refusal a boot meets on such a machine, about one backend or one profile; it names the
cleanup instead.

The home is the v0.72 kit, copied from that release's wheel.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.doctor_cmd import PendingMigrationsFinding, check_backend_credentials, check_models, check_pending_migrations
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.migration.former_release import RETIRED_BACKEND_NAMES, SERVICE_FILE_NAME
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
    SERVICE_FILE_NAME,
    f"{INFERENCE_DIR_NAME}/{ROUTING_PROFILES_FILE_NAME}",
]


@pytest.fixture
def former_release_home(tmp_path: Path, mocker: MockerFixture) -> Path:
    """A fake home holding the v0.72 kit, and a project without a `.pipelex/`, so the walk reads this test's files."""
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".pipelex"
    shutil.copytree(V0_72_CONFIG_DIR, config_dir)
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)
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
