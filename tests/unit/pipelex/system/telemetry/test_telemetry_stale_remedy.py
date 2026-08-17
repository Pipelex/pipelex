"""A telemetry configuration that will not load says whether it is old or wrong.

Before the ledger, every telemetry failure got one answer — *the format changed, run
`pipelex init telemetry`* — written for one real event and then shown for every other way a file
can fail. That remedy writes a fresh file, so on the very case it named it discarded the PostHog
key, the Langfuse credentials and the OTLP exporters it was supposed to be helping with.

Boot tolerance now carries an old file forward on its own, so anything reaching this error is
either a file the ledger cannot *fully* explain or one that is genuinely invalid. Telling those
two apart is what the migration block on the error is for, and every surface that reports the
failure — the human CLI, the agent envelope, the doctor — branches on that block rather than on
the wording.

The stale documents here are the package's own: `telemetry-config@2` is the shipped entry and
`goldens/telemetry-config/before@2.toml` is the flat document it exists to carry forward.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.system.configuration.config_surface import TELEMETRY_CONFIG_SURFACE_ID
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.system.telemetry.telemetry_loader import load_telemetry_config
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# A realistic PostHog project key, planted in the file the error is raised about. The old flat
# format is exactly where a user's real one would be, which is what makes it the right specimen
# for the rendering rule on this channel.
PLANTED_KEY = "phc_L1VE_telemetry_key_that_must_never_be_rendered"

UNKNOWN_KEY = "not_a_telemetry_setting"


def old_shape_document() -> str:
    """The flat pre-`[custom_posthog]` document the shipped entry is about, read from the package."""
    path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
    return path.read_text(encoding="utf-8")


@pytest.fixture
def global_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """A fake home, so the loader and the scan both read this test's files rather than the machine's."""
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".pipelex"
    config_dir.mkdir(parents=True)

    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    (project_root / ".pipelex").mkdir()

    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)

    return config_dir


def load_and_capture(*, config_dir: Path, body: str) -> TelemetryConfigValidationError:
    """Write a telemetry file that will not load, and hand back the refusal it produces."""
    (config_dir / "telemetry.toml").write_text(body, encoding="utf-8")
    with pytest.raises(TelemetryConfigValidationError) as caught:
        load_telemetry_config(secrets_provider=EnvSecretsProvider())
    return caught.value


class TestTheErrorSaysWhetherTheFileIsOldOrWrong:
    """The block is the verdict; a consumer branches on its presence and never on the wording."""

    def test_a_file_the_ledger_only_half_explains_carries_the_pending_migration(self, global_dir: Path) -> None:
        """The reachable specimen, and the one boot tolerance leaves behind.

        A file that is flat *and* carries a key no telemetry schema ever had: the replay does real
        work, the re-validation fails anyway, and what the user is left holding is a file that is
        both old and wrong. Saying only the second half is what sent them to a destructive remedy.
        """
        exc = load_and_capture(config_dir=global_dir, body=f"{old_shape_document()}\n{UNKNOWN_KEY} = true\n")

        assert exc.migration is not None
        assert exc.migration.remedy == MIGRATE_COMMAND
        assert [plan.file_path for plan in exc.migration.plans] == [global_dir / "telemetry.toml"]
        assert MIGRATE_COMMAND in exc.message

    def test_a_file_that_is_simply_wrong_carries_no_block_at_all(self, global_dir: Path) -> None:
        """Absence is a verdict too — this configuration is not stale, and no command repairs it."""
        exc = load_and_capture(config_dir=global_dir, body='[custom_posthog]\nmode = "no-such-mode"\n')

        assert exc.migration is None
        assert MIGRATE_COMMAND not in exc.message
        assert "custom_posthog.mode" in exc.message

    def test_a_key_no_build_knows_is_named_even_with_nothing_to_migrate(self, global_dir: Path) -> None:
        """The diagnosis speaks on its own: an unknown root key is a finding without a single step."""
        exc = load_and_capture(config_dir=global_dir, body=f"{UNKNOWN_KEY} = true\n")

        assert exc.migration is not None
        assert exc.migration.needs_attention is True
        assert [unexplained.path for plan in exc.migration.plans for unexplained in plan.unexplained] == [UNKNOWN_KEY]

    def test_the_domain_comes_from_the_class_and_the_block_rides_the_report(self, global_dir: Path) -> None:
        """What an agent consumer actually reads: one structured envelope, `config` either way."""
        exc = load_and_capture(config_dir=global_dir, body=f"{old_shape_document()}\n{UNKNOWN_KEY} = true\n")

        report = exc.to_error_report()

        assert report.error_domain == "config"
        assert report.migration is not None
        assert report.to_dict()["migration"]["remedy"] == MIGRATE_COMMAND

    def test_no_remedy_ever_tells_a_reader_to_start_the_file_over(self, global_dir: Path) -> None:
        """The whole point of the change: a migratable file is never answered with a reset."""
        exc = load_and_capture(config_dir=global_dir, body=f"{old_shape_document()}\n{UNKNOWN_KEY} = true\n")

        assert "init telemetry" not in exc.message


class TestNoValueFromAUsersFileIsEverRendered:
    """The mechanical rule, on the telemetry surface's own error.

    The document carries a realistic PostHog key at the exact path the shipped entry moves, and it
    must appear in neither half of what the error hands on — not in the sentence a human reads,
    not in the structured block a machine parses — while the file demonstrably still holds it.
    """

    def test_the_planted_key_is_in_the_file_and_in_neither_half_of_the_error(self, global_dir: Path) -> None:
        stale = old_shape_document().replace('project_api_key = "phc_example_project_api_key"', f'project_api_key = "{PLANTED_KEY}"')
        assert PLANTED_KEY in stale, "the specimen must actually carry the secret"

        exc = load_and_capture(config_dir=global_dir, body=f"{stale}\n{UNKNOWN_KEY} = true\n")

        assert PLANTED_KEY in (global_dir / "telemetry.toml").read_text(encoding="utf-8")
        assert PLANTED_KEY not in exc.message
        assert exc.migration is not None
        assert PLANTED_KEY not in str(exc.migration.model_dump(mode="json"))


class TestTheRemedyIsNamedOnlyWhereItWouldWrite:
    """A block says the migration history has something to report; it does not say a command fixes it.

    The two specimens below produce the same structured shape — a block, on a `telemetry.toml` that
    refused — and the same command would do opposite things to them. One is rewritten and repaired;
    the other is read, left untouched, and still refuses afterwards.
    """

    def test_a_file_the_ledger_carries_forward_is_told_to_run_the_command(self, global_dir: Path) -> None:
        exc = load_and_capture(config_dir=global_dir, body=f"{old_shape_document()}\n{UNKNOWN_KEY} = true\n")

        assert exc.migration is not None
        assert exc.migration.would_write is True
        # The specimen is both old and wrong, so the command is named for what it carries forward
        # and the unknown key is left where it belongs — with a person.
        assert f"Run `{MIGRATE_COMMAND}` to carry forward what it can; the rest is yours to fix." in exc.message

    def test_a_file_with_nothing_to_apply_is_told_to_read_the_dry_run(self, global_dir: Path) -> None:
        """An unknown root key on a file that is otherwise current: a finding without a single step."""
        exc = load_and_capture(config_dir=global_dir, body=f'[custom_posthog]\nmode = "off"\n{UNKNOWN_KEY} = true\n')

        assert exc.migration is not None
        assert exc.migration.would_write is False
        assert f"Run `{MIGRATE_COMMAND}` to bring these files up to date." not in exc.message
        assert f"{MIGRATE_COMMAND} --dry-run" in exc.message
