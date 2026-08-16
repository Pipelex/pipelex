"""Boot tolerance — a stale configuration warns instead of stopping the world.

The failure this is about is ordinary and unpleasant: a schema change lands, the file on the
machine is the old shape, and the next boot dies on `extra="forbid"` with a pydantic error naming
a key the user never chose to have. Tolerance replays the surface's ledger over the same files
**in memory**, validates what comes back, and boots with a warning if that succeeds.

Two properties carry the whole design, and most of the tests below exist to hold one of them:

- **Boot tolerates only what the ledger explains.** Anything else raises exactly what it raised
  before. The retry either recovers or gets out of the way — it never softens an error.
- **Boot never writes.** Only the explicit `migrate` command does. A tolerated boot leaves the
  file exactly as it found it, backups included, which is why the same warning keeps appearing
  until the user runs the command.

The stale documents here are **real**: `telemetry-config@2` is the entry the package ships and
`goldens/telemetry-config/before@2.toml` is the flat document it exists to carry forward, read
live rather than copied. The other two surfaces have empty ledgers today, so their tests plant a
synthetic one in a temporary migration directory — the wiring is what is under test there, and a
synthetic ledger tests it without inventing a schema change nobody made.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.system.configuration import config_surface as config_surface_module
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.configuration.config_surface import (
    PIPELEX_CONFIG_SURFACE_ID,
    PIPELEX_SERVICE_CONFIG_SURFACE_ID,
    TELEMETRY_CONFIG_SURFACE_ID,
    replay_surface_files_in_memory,
    stale_configuration_warning,
)
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.exceptions import ConfigValidationError
from pipelex.system.pipelex_service.exceptions import PipelexServiceConfigValidationError
from pipelex.system.pipelex_service.pipelex_service_config import load_pipelex_service_config_if_exists
from pipelex.system.telemetry import telemetry_config as telemetry_config_module
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig, load_telemetry_config
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def old_shape_telemetry_document() -> str:
    """The flat pre-`[custom_posthog]` document the shipped entry is about, read from the package."""
    path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
    return path.read_text(encoding="utf-8")


def write_synthetic_ledger(*, migration_dir: Path, surface_id: str, base_file: str, ops_body: str) -> None:
    """A one-entry ledger for a surface whose real ledger has nothing in it yet."""
    ledgers_dir = migration_dir / "ledgers"
    ledgers_dir.mkdir(parents=True, exist_ok=True)
    (ledgers_dir / f"{surface_id}.toml").write_text(
        f"""
[surface]
id = "{surface_id}"
title = "A surface under test"
base_file = "{base_file}"
current_schema_version = 2
min_supported_schema_version = 0

[[migration]]
id = "{surface_id}@2"
to_schema_version = 2
introduced_in = "0.46.0"
breaking = true
safety = "safe"
title = "Give the setting its current name"
description = "The setting was renamed and this entry carries a file written before that onto the current shape."

{ops_body}
""",
        encoding="utf-8",
    )


@pytest.fixture
def fake_dirs(tmp_path: Path, mocker: MockerFixture) -> tuple[Path, Path]:
    """A fake home and project tree, so a loader reads test files rather than the machine's own."""
    fake_home = tmp_path / "home"
    global_dir = fake_home / ".pipelex"
    global_dir.mkdir(parents=True)

    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    project_dir = project_root / ".pipelex"
    project_dir.mkdir()

    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)

    return global_dir, project_dir


@pytest.fixture
def secrets_provider() -> EnvSecretsProvider:
    return EnvSecretsProvider()


@pytest.fixture
def synthetic_migration_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point the boot-tolerance helper at a migration directory this test owns."""
    migration_dir = tmp_path / "migration"
    mocker.patch.object(config_surface_module, "packaged_migration_dir", return_value=migration_dir)
    return migration_dir


class TestReplayingASurfaceInMemory:
    """The shared helper, against the ledger and the old-shape document the package ships."""

    def test_a_current_file_is_nothing_the_ledger_has_to_say_about(self, tmp_path: Path) -> None:
        """`None` is the answer that keeps a healthy machine out of every branch below."""
        current = tmp_path / "telemetry.toml"
        current.write_text('[custom_posthog]\nmode = "off"\n', encoding="utf-8")

        assert replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[current]) is None

    def test_an_old_shape_file_comes_back_carried_forward(self, tmp_path: Path) -> None:
        stale = tmp_path / "telemetry.toml"
        stale.write_text(old_shape_telemetry_document(), encoding="utf-8")

        replayed = replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[stale])

        assert replayed is not None
        assert "telemetry_mode" not in replayed.config_dict, "the flat key is what the entry moves away"
        assert TelemetryConfig.model_validate(replayed.config_dict).custom_posthog is not None
        assert [step.entry_id for step in replayed.plans[0].steps] == ["telemetry-config@2"]

    def test_the_file_on_disk_is_not_touched(self, tmp_path: Path) -> None:
        """Boot never writes. Only `pipelex migrate` does, which is why the warning keeps coming back."""
        stale = tmp_path / "telemetry.toml"
        stale.write_text(old_shape_telemetry_document(), encoding="utf-8")
        before = stale.read_bytes()

        replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[stale])

        assert stale.read_bytes() == before
        assert list(tmp_path.iterdir()) == [stale], "a boot leaves no backup beside the file either"

    def test_a_missing_file_is_skipped_and_the_files_beside_it_still_merge(self, tmp_path: Path) -> None:
        """Every layer of a surface is optional, exactly as it is on the ordinary load path."""
        stale = tmp_path / "telemetry.toml"
        stale.write_text(old_shape_telemetry_document(), encoding="utf-8")

        replayed = replay_surface_files_in_memory(
            surface_id=TELEMETRY_CONFIG_SURFACE_ID,
            paths=[tmp_path / "telemetry_override.toml", stale, tmp_path / "telemetry_local.toml"],
        )

        assert replayed is not None
        assert len(replayed.plans) == 1, "a file that is not there is not a file the report is about"

    def test_a_later_layer_wins_on_a_key_both_carry(self, tmp_path: Path) -> None:
        """The merge order is the loader's, so the tolerated configuration is the same one."""
        base = tmp_path / "telemetry.toml"
        base.write_text('telemetry_mode = "off"\n', encoding="utf-8")
        override = tmp_path / "telemetry_override.toml"
        override.write_text('telemetry_mode = "anonymous"\n', encoding="utf-8")

        replayed = replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[base, override])

        assert replayed is not None
        assert replayed.config_dict["custom_posthog"]["mode"] == PostHogMode.ANONYMOUS

    def test_a_file_that_cannot_be_parsed_abandons_the_whole_retry(self, tmp_path: Path) -> None:
        """Skipping it would drop a layer, and a retry that then validated would boot on a
        configuration the user does not have. The file's own parse error is the one to show.
        """
        stale = tmp_path / "telemetry.toml"
        stale.write_text(old_shape_telemetry_document(), encoding="utf-8")
        broken = tmp_path / "telemetry_override.toml"
        broken.write_text("this is not = = toml\n", encoding="utf-8")

        assert replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[stale, broken]) is None

    def test_the_reserved_meta_table_is_stripped(self, tmp_path: Path) -> None:
        """The helper replaces the loader's read-and-merge, so it owes the strip that came with it."""
        stale = tmp_path / "telemetry.toml"
        # Root keys before the table header, because a header absorbs every scalar that follows it.
        stale.write_text('telemetry_mode = "off"\n\n[meta]\nschema_version = 1\n', encoding="utf-8")

        replayed = replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[stale])

        assert replayed is not None
        assert "meta" not in replayed.config_dict


class TestWhatTheWarningSays:
    def test_it_names_the_file_and_the_remedy(self, tmp_path: Path) -> None:
        stale = tmp_path / "telemetry.toml"
        stale.write_text(old_shape_telemetry_document(), encoding="utf-8")
        replayed = replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[stale])
        assert replayed is not None

        warning = stale_configuration_warning(plans=replayed.plans)

        assert str(stale) in warning
        assert "pipelex migrate" in warning
        assert "Nothing was written" in warning

    def test_it_says_what_the_ledger_carried_and_nothing_read_from_the_file(self, tmp_path: Path) -> None:
        """Ledger text only, the same rule the migration report obeys — a boot warning is read in
        the same places a report is, and a user's own values have no business in either.
        """
        stale = tmp_path / "telemetry.toml"
        stale.write_text('telemetry_mode = "off"\nproject_api_key = "phc_a_secret_the_user_owns"\n', encoding="utf-8")
        replayed = replay_surface_files_in_memory(surface_id=TELEMETRY_CONFIG_SURFACE_ID, paths=[stale])
        assert replayed is not None

        warning = stale_configuration_warning(plans=replayed.plans)

        assert "Nest the flat telemetry settings under [custom_posthog]" in warning
        assert "phc_a_secret_the_user_owns" not in warning


class TestTheTelemetryLoader:
    """The one surface whose shipped ledger already carries a real entry."""

    def test_an_old_shape_file_boots_with_a_warning(
        self,
        fake_dirs: tuple[Path, Path],
        secrets_provider: EnvSecretsProvider,
        mocker: MockerFixture,
    ) -> None:
        global_dir, _ = fake_dirs
        stale = global_dir / "telemetry.toml"
        stale.write_text(old_shape_telemetry_document(), encoding="utf-8")
        before = stale.read_bytes()
        warning = mocker.patch.object(telemetry_config_module.log, "warning")

        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.custom_posthog is not None
        assert stale.read_bytes() == before, "a tolerated boot writes nothing"
        assert "pipelex migrate" in warning.call_args.args[0]

    def test_a_file_the_ledger_cannot_explain_still_raises(
        self,
        fake_dirs: tuple[Path, Path],
        secrets_provider: EnvSecretsProvider,
    ) -> None:
        """Tolerance widens what starts; it never widens what is silently accepted."""
        global_dir, _ = fake_dirs
        (global_dir / "telemetry.toml").write_text("not_a_telemetry_setting = true\n", encoding="utf-8")

        with pytest.raises(TelemetryConfigValidationError):
            load_telemetry_config(secrets_provider=secrets_provider)

    def test_a_file_the_ledger_only_half_explains_raises_the_original_error(
        self,
        fake_dirs: tuple[Path, Path],
        secrets_provider: EnvSecretsProvider,
    ) -> None:
        """The branch where the retry does real work and still does not get there.

        This file is flat *and* carries a key no telemetry schema ever had, so the replay applies
        — the entry's operations fire — and the re-validation fails anyway. Tolerance widens what
        starts, never what is accepted, so what the user sees is the error their file produces.
        """
        global_dir, _ = fake_dirs
        (global_dir / "telemetry.toml").write_text('telemetry_mode = "off"\nnot_a_telemetry_setting = true\n', encoding="utf-8")

        with pytest.raises(TelemetryConfigValidationError, match="not_a_telemetry_setting"):
            load_telemetry_config(secrets_provider=secrets_provider)

    def test_an_old_shape_tier_file_is_carried_forward_too(
        self,
        fake_dirs: tuple[Path, Path],
        secrets_provider: EnvSecretsProvider,
    ) -> None:
        """The retry covers every layer the loader merged, not only the base file."""
        global_dir, project_dir = fake_dirs
        (global_dir / "telemetry.toml").write_text('[custom_posthog]\nmode = "off"\n', encoding="utf-8")
        (project_dir / "telemetry_override.toml").write_text('telemetry_mode = "anonymous"\n', encoding="utf-8")

        config = load_telemetry_config(secrets_provider=secrets_provider)

        assert config.custom_posthog is not None
        assert config.custom_posthog.mode is PostHogMode.ANONYMOUS

    @pytest.mark.usefixtures("fake_dirs")
    def test_a_healthy_configuration_never_reaches_the_ledger(
        self,
        secrets_provider: EnvSecretsProvider,
        mocker: MockerFixture,
    ) -> None:
        """The replay runs on the failure path only, so a current machine pays nothing for it."""
        retry = mocker.spy(telemetry_config_module, "replay_surface_files_in_memory")

        load_telemetry_config(secrets_provider=secrets_provider)

        assert retry.call_count == 0


class TestTheMainConfigurationLoader:
    def test_an_old_shape_file_is_validated_after_the_replay(
        self,
        fake_dirs: tuple[Path, Path],
        synthetic_migration_dir: Path,
        mocker: MockerFixture,
    ) -> None:
        """And the *migrated* value is the one that lands, not merely a configuration that parses."""
        global_dir, _ = fake_dirs
        write_synthetic_ledger(
            migration_dir=synthetic_migration_dir,
            surface_id=PIPELEX_CONFIG_SURFACE_ID,
            base_file="pipelex.toml",
            ops_body='[[migration.ops]]\nkind = "rename_table_key"\ntable_path = ["pipelex", "log_config"]\n'
            'key = "old_default_log_level"\nnew_key = "default_log_level"\n',
        )
        (global_dir / "pipelex.toml").write_text('[pipelex.log_config]\nold_default_log_level = "DEBUG"\n', encoding="utf-8")
        warning = mocker.patch("pipelex.system.configuration.config_loader.log.warning")

        config = ConfigLoader().load_config_validated(config_cls=PipelexConfig)

        assert config.pipelex.log_config.default_log_level is LogLevel.DEBUG
        assert "pipelex migrate" in warning.call_args.args[0]

    def test_programmatic_overrides_are_re_applied_over_the_replay(
        self,
        fake_dirs: tuple[Path, Path],
        synthetic_migration_dir: Path,
    ) -> None:
        """They are a layer of the load rather than a property of the files, and the replay only
        ever sees the files — so a retry that forgot them would boot a different configuration.
        """
        global_dir, _ = fake_dirs
        write_synthetic_ledger(
            migration_dir=synthetic_migration_dir,
            surface_id=PIPELEX_CONFIG_SURFACE_ID,
            base_file="pipelex.toml",
            ops_body='[[migration.ops]]\nkind = "rename_table_key"\ntable_path = ["pipelex", "log_config"]\n'
            'key = "old_default_log_level"\nnew_key = "default_log_level"\n',
        )
        (global_dir / "pipelex.toml").write_text('[pipelex.log_config]\nold_default_log_level = "DEBUG"\n', encoding="utf-8")

        config = ConfigLoader().load_config_validated(
            config_cls=PipelexConfig,
            extra_overrides={"pipelex": {"log_config": {"default_log_level": "WARNING"}}},
        )

        assert config.pipelex.log_config.default_log_level is LogLevel.WARNING

    @pytest.mark.usefixtures("fake_dirs", "synthetic_migration_dir")
    def test_a_configuration_the_ledger_cannot_explain_still_raises_the_users_own_error(self) -> None:
        """And the message still names the key, which is the only thing that tells them what to fix.

        The migration directory here holds no ledger at all, so the retry cannot even be attempted
        — the case that proves a failure *inside* the retry never replaces the failure outside it.
        """
        with pytest.raises(ConfigValidationError, match="not_a_real_setting"):
            ConfigLoader().load_config_validated(
                config_cls=PipelexConfig,
                extra_overrides={"not_a_real_setting": True},
            )

    @pytest.mark.usefixtures("fake_dirs")
    def test_a_healthy_configuration_never_reaches_the_ledger(self, mocker: MockerFixture) -> None:
        retry = mocker.spy(ConfigLoader, "_config_the_ledger_can_explain")

        ConfigLoader().load_config_validated(config_cls=PipelexConfig)

        assert retry.call_count == 0


class TestTheServiceConfigLoader:
    """One file, no tiers — the merge the shared helper performs is a merge of one."""

    def test_an_old_shape_file_boots_with_a_warning(self, tmp_path: Path, synthetic_migration_dir: Path, mocker: MockerFixture) -> None:
        write_synthetic_ledger(
            migration_dir=synthetic_migration_dir,
            surface_id=PIPELEX_SERVICE_CONFIG_SURFACE_ID,
            base_file="pipelex_service.toml",
            ops_body='[[migration.ops]]\nkind = "rename_table_key"\ntable_path = []\nkey = "terms"\nnew_key = "agreement"\n',
        )
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        stale = config_dir / "pipelex_service.toml"
        stale.write_text("[terms]\nterms_accepted = true\n", encoding="utf-8")
        warning = mocker.patch("pipelex.system.pipelex_service.pipelex_service_config.log.warning")

        config = load_pipelex_service_config_if_exists(config_dir=config_dir)

        assert config is not None
        assert config.agreement.terms_accepted is True
        assert stale.read_bytes() == b"[terms]\nterms_accepted = true\n", "a tolerated boot writes nothing"
        assert "pipelex migrate" in warning.call_args.args[0]

    @pytest.mark.usefixtures("synthetic_migration_dir")
    def test_a_file_the_ledger_cannot_explain_still_raises(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "pipelex_service.toml").write_text("[nonsense]\nwhat = true\n", encoding="utf-8")

        with pytest.raises(PipelexServiceConfigValidationError):
            load_pipelex_service_config_if_exists(config_dir=config_dir)
