"""End-to-end tests for ``pipelex migrate`` and ``pipelex-agent migrate``, via subprocess.

Both binaries live in one module because the *scenario* is one: a machine whose configuration
files predate the installed pipelex, a boot that fails because of it, and a command that repairs
it. Splitting the module would duplicate the only hard part — planting that machine — and the two
commands would then be proved against two subtly different ones.

**The old shape is real, and so is the migration.** The fixture is the package's own
``goldens/telemetry-config/before@2.toml``, the hand-authored flat document that entry
``telemetry-config@2`` exists to carry forward, read live rather than copied here. The ledger that
migrates it is the one the package ships. Nothing about this test is synthetic except the machine
it runs on, which is what makes the state it starts from a real one: a flat ``telemetry.toml``
fails ``TelemetryConfig``'s ``extra="forbid"`` today, in the field.

**Boot tolerance is why that machine boots at all.** Such a machine used to die at boot; it now
starts, carries the file forward in memory, and warns a person that it did. So the boot probe here
no longer measures "broken, then fixed" — it asserts the machine boots on *both* sides of every
command, which is the tolerance property itself, while what the command changed is measured on the
files. The warning is not asserted here and cannot be: this probe is the agent CLI, which silences
logging process-wide by contract. It is asserted per surface in ``test_boot_tolerance.py``,
alongside the other half — a configuration the ledger cannot explain still fails the boot.

The boot probe is ``pipelex-agent models``: the cheapest command that performs a full Pipelex boot,
including the telemetry load the old shape sends down the tolerance path. ``pipelex show config``
is not a probe — it exits 0 on a machine whose telemetry configuration cannot load, because it
never reads it.
"""

from __future__ import annotations

import json
import subprocess  # noqa: S404 - invokes the real pipelex binaries for E2E coverage
from typing import TYPE_CHECKING, Any

from pipelex.migration.backup import existing_backups_of
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.tools.misc.toml_utils import load_toml_from_path
from tests.e2e.agent_cli.conftest import REPO_ROOT

if TYPE_CHECKING:
    from pathlib import Path

PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
PIPELEX_AGENT_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex-agent"

TELEMETRY_SURFACE_ID = "telemetry-config"

# A tier file of the flat era, as a user would have written one: a couple of overrides on top of
# the global file, not the whole census the golden carries.
OLD_SHAPE_PROJECT_OVERRIDE = """\
# My project keeps telemetry quiet.
telemetry_mode = "off"
host = "https://project.example.invalid"
"""


def _old_shape_telemetry_document() -> str:
    """The flat pre-history document the shipped entry is about, read from the package."""
    path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_SURFACE_ID, schema_version=2)
    return path.read_text(encoding="utf-8")


def _plant_a_stale_machine(*, hermetic_home: Path) -> tuple[Path, Path, Path]:
    """A machine with an old-shape file in the global directory and another in a project.

    Both directories are walked and both files are claimed — the global ``telemetry.toml`` by the
    surface's base file and the project ``telemetry_override.toml`` by its tier glob — so the run
    has to reach two directories and two tiers to be complete. The project override is also the
    tier the telemetry loader actually merges, which is what keeps the boot failure honest.

    Returns the project directory, the global file and the project file.
    """
    global_file = hermetic_home / ".pipelex" / "telemetry.toml"
    global_file.write_text(_old_shape_telemetry_document(), encoding="utf-8")

    project_dir = hermetic_home / "workspace"
    project_config_dir = project_dir / ".pipelex"
    project_config_dir.mkdir(parents=True)
    project_file = project_config_dir / "telemetry_override.toml"
    project_file.write_text(OLD_SHAPE_PROJECT_OVERRIDE, encoding="utf-8")
    return project_dir, global_file, project_file


def _run(*, args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # A wide terminal, because the human CLI renders through Rich and Rich wraps at the console
    # width. A temp-directory path is long enough to be broken across two lines at the default 80,
    # which would make these assertions fail for a reason that has nothing to do with migration.
    return subprocess.run(  # noqa: S603
        args,
        env={**env, "COLUMNS": "400"},
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def _boot(*, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command that performs a full Pipelex boot, telemetry load included."""
    return _run(args=[str(PIPELEX_AGENT_BIN), "models", "--format", "json"], env=env, cwd=cwd)


def _assert_boots(*, env: dict[str, str], cwd: Path) -> None:
    """Boot tolerance, through the real binaries: a machine carrying the old shape starts anyway.

    Asserted on both sides of every command here, which is deliberate — a before/after that only
    checked *after* would pass just as well if the file had never been stale.

    It does **not** assert the warning, and cannot: this probe is ``pipelex-agent``, which cuts
    Python's logging off process-wide as its first act so that nothing pollutes its two structured
    streams. That is the agent CLI's contract working, not a gap — the warning is where a person
    reads it, and it is asserted per surface in ``test_boot_tolerance.py``. What it does mean is
    that a *machine* consumer never learns of a pending migration from a boot, only by asking:
    ``pipelex-agent migrate --dry-run``, or the `doctor` row.
    """
    booted = _boot(env=env, cwd=cwd)
    assert booted.returncode == 0, booted.stderr


class TestTheHumanMigrateCommand:
    def test_stale_files_in_both_directories_are_migrated_and_the_boot_stops_warning(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, global_file, project_file = _plant_a_stale_machine(hermetic_home=hermetic_home)

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

        migrated = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=project_dir)

        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        # The human CLI's console writes to stderr when no runtime hub owns one, which is the case
        # for a command that deliberately does not boot. Read both, and assert on the union.
        report = migrated.stdout + migrated.stderr
        assert str(global_file) in report
        assert str(project_file) in report

        assert load_toml_from_path(path=global_file) == {
            "custom_posthog": {
                "mode": "anonymous",
                "endpoint": "https://eu.i.posthog.com",
                "api_key": "phc_example_project_api_key",
                "user_id": "",
                "geoip": True,
                "debug": False,
                "redact_properties": ["prompt", "system_prompt", "response", "file_path", "url"],
            }
        }
        assert load_toml_from_path(path=project_file) == {"custom_posthog": {"mode": "off", "endpoint": "https://project.example.invalid"}}

        # One copy per file, holding what that file used to say. Exactly one: a run that backed a
        # file up twice, or left an older copy beside the new one, would be leaving the user to
        # work out which is the original.
        for original, path in ((_old_shape_telemetry_document(), global_file), (OLD_SHAPE_PROJECT_OVERRIDE, project_file)):
            backups = existing_backups_of(path=path)
            assert len(backups) == 1, f"expected exactly one backup of {path}, found {backups}"
            assert backups[0].read_text(encoding="utf-8") == original

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

    def test_a_dry_run_reports_the_same_work_and_writes_nothing(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, global_file, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)
        original = global_file.read_text(encoding="utf-8")

        planned = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--dry-run"], env=offline_subprocess_env, cwd=project_dir)

        assert planned.returncode == 0, planned.stdout + planned.stderr
        assert "telemetry-config@2" in planned.stdout + planned.stderr or "Nest the flat telemetry" in planned.stdout + planned.stderr
        assert global_file.read_text(encoding="utf-8") == original
        assert existing_backups_of(path=global_file) == []

    def test_the_two_write_flags_contradict_each_other_and_are_refused(
        self,
        hermetic_home: Path,  # noqa: ARG002 - the fixture is what makes HOME hermetic for the subprocess
        offline_subprocess_env: dict[str, str],
    ) -> None:
        refused = _run(
            args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--dry-run", "--yes"],
            env=offline_subprocess_env,
            cwd=REPO_ROOT,
        )

        assert refused.returncode == 2
        assert "contradict" in refused.stdout + refused.stderr


class TestTheAgentMigrateLoop:
    def test_plan_as_json_then_apply_and_the_boot_stops_warning(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, global_file, project_file = _plant_a_stale_machine(hermetic_home=hermetic_home)

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

        planned = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=project_dir,
        )
        assert planned.returncode == 0, planned.stderr
        plan: dict[str, Any] = json.loads(planned.stdout)

        assert plan["applied"] is False
        assert plan["needs_attention"] is False
        assert plan["is_clean"] is False
        assert plan["summary"]["files_changed"] == 2
        assert plan["summary"]["files_written"] == 0
        assert existing_backups_of(path=global_file) == [], "a plan is not a write"
        assert {str(hermetic_home / ".pipelex"), str(project_dir / ".pipelex")} == set(plan["config_dirs"])

        applied = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)
        assert applied.returncode == 0, applied.stderr
        outcome: dict[str, Any] = json.loads(applied.stdout)

        assert outcome["applied"] is True
        assert outcome["summary"]["files_written"] == 2
        written = {plan_dict["file_path"] for plan_dict in outcome["plans"] if plan_dict["was_written"]}
        assert written == {str(global_file), str(project_file)}

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

    def test_a_second_run_finds_nothing_left_to_do(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """Replay neutrality, at the command's own level: migrating twice is migrating once."""
        project_dir, _, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)

        first = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)
        assert first.returncode == 0, first.stderr

        second = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)
        assert second.returncode == 0, second.stderr
        outcome: dict[str, Any] = json.loads(second.stdout)
        assert outcome["is_clean"] is True
        assert outcome["summary"]["files_written"] == 0

    def test_the_two_write_flags_contradict_each_other_and_are_refused(
        self,
        hermetic_home: Path,  # noqa: ARG002 - the fixture is what makes HOME hermetic for the subprocess
        offline_subprocess_env: dict[str, str],
    ) -> None:
        refused = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--yes", "--format", "json"],
            env=offline_subprocess_env,
            cwd=REPO_ROOT,
        )

        assert refused.returncode == 2
        assert json.loads(refused.stderr)["error_type"] == "ArgumentError"


class TestTheBootstrapPath:
    """The property that makes this command reachable at all: it runs when nothing else does.

    A broken configuration is the reason to reach for `migrate`, so needing a working one would
    make it useless in exactly the case it exists for. What it may use is the migration ledger, the
    applier and the filesystem — and this test is what keeps a future import of the config, the
    model deck or the network from creeping into that list unnoticed.
    """

    def _break_the_configuration(self, *, hermetic_home: Path) -> None:
        config_file = hermetic_home / ".pipelex" / "pipelex.toml"
        # At the top of the document, so the key lands at the root rather than in whichever table
        # happens to be last — a root key no model knows, which no ledger entry removes either.
        config_file.write_text(f"not_a_real_setting = true\n{config_file.read_text(encoding='utf-8')}", encoding="utf-8")

    def test_both_commands_run_against_a_configuration_that_cannot_load(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        self._break_the_configuration(hermetic_home=hermetic_home)

        boot = _boot(env=offline_subprocess_env, cwd=hermetic_home)
        assert boot.returncode != 0, "the scenario is worthless if this machine boots"
        # `PipelexConfigError` rather than the raw `ConfigValidationError` this used to report:
        # the boot's own arm now catches both shapes a refusal takes and translates. The class is
        # what carries `error_domain: "config"` and the `migration` block to a machine consumer.
        assert "PipelexConfigError" in boot.stderr

        # Both commands answer with a *report* rather than a crash, and that — not the exit code —
        # is what "it runs" means here. Each leaves a 1 behind, because the key planted above is
        # one the downgrade diagnosis has something to say about; the test below is what says so.
        human = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--dry-run"], env=offline_subprocess_env, cwd=hermetic_home)
        assert human.returncode == 1, human.stdout + human.stderr
        assert str(hermetic_home / ".pipelex") in human.stdout + human.stderr

        agent = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=hermetic_home,
        )
        assert agent.returncode == 1, agent.stderr
        assert json.loads(agent.stdout)["summary"]["files_walked"] > 0

    def test_the_root_key_no_ledger_removes_is_named_rather_than_passed_over(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The downgrade diagnosis, against the very file that broke the boot.

        A replay finds nothing to do here — no operation's source is present — so without the
        diagnosis the command would report this machine clean beside a boot that will not start,
        which is the exact failure the migration project exists to remove.
        """
        self._break_the_configuration(hermetic_home=hermetic_home)

        planned = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=hermetic_home,
        )

        assert planned.returncode == 1, "an unexplained path is a person's to resolve, so the run needs attention"
        report: dict[str, Any] = json.loads(planned.stdout)
        assert report["needs_attention"] is True
        assert report["summary"]["unexplained_paths"] == 1
        unexplained = [found for plan in report["plans"] if plan["file_path"].endswith("pipelex.toml") for found in plan["unexplained"]]
        assert [found["path"] for found in unexplained] == ["not_a_real_setting"]
        assert "newer pipelex" in unexplained[0]["note"]

    def test_the_ledger_still_migrates_a_stale_file_beside_a_configuration_that_cannot_load(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The bootstrap path is not merely "does not crash" — it still does the work.

        A command that ran but declined to touch anything while the configuration was broken would
        pass the test above and be useless.
        """
        self._break_the_configuration(hermetic_home=hermetic_home)
        _, global_file, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)

        applied = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"],
            env=offline_subprocess_env,
            cwd=hermetic_home,
        )

        # A 1, and the work still done: the broken `pipelex.toml` beside it is a file the diagnosis
        # has something to say about, and one file needing a human never stops another being
        # migrated. That is the per-file scope, read at the level of the whole command.
        assert applied.returncode == 1, applied.stderr
        outcome: dict[str, Any] = json.loads(applied.stdout)
        assert outcome["summary"]["files_written"] == 1
        assert outcome["summary"]["unexplained_paths"] == 1
        assert "custom_posthog" in global_file.read_text(encoding="utf-8")


class TestNoValueFromAUsersFileIsEverRendered:
    """The contract's mechanical rule, asserted on the channels that exist today.

    > No value read from a user's file is ever rendered — not in the command's output, not in the
    > structured plan, not in an error.

    Mechanical rather than a list of credential-shaped key names, because such a list is a guess
    that eventually misses one. The planted value is carried by a `move_key` the shipped ledger
    performs, so the run demonstrably *handled* it — a rule that held only because the value was
    quietly dropped would be no rule at all.

    Two of the three channels are covered here: the command's own output and the structured plan.
    The third — the `migration` block on a configuration validation error — is
    `TestABootFailureCarriesThePendingMigration` below, which needs a different specimen: boot
    tolerance means a file the ledger *can* explain never reaches an error surface at all.
    """

    PLANTED_SECRET = "phc_L1VE_s3cret_project_key_that_must_never_be_rendered"

    def _plant_the_secret(self, *, hermetic_home: Path) -> tuple[Path, Path]:
        document = _old_shape_telemetry_document().replace("phc_example_project_api_key", self.PLANTED_SECRET)
        assert self.PLANTED_SECRET in document, "the golden no longer carries the api key this test substitutes into"
        project_dir, global_file, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)
        global_file.write_text(document, encoding="utf-8")
        return project_dir, global_file

    def test_neither_command_renders_a_planted_secret_while_migrating_it(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, global_file = self._plant_the_secret(hermetic_home=hermetic_home)

        channels = [
            _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--dry-run"], env=offline_subprocess_env, cwd=project_dir),
            _run(
                args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
                env=offline_subprocess_env,
                cwd=project_dir,
            ),
            _run(
                args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "markdown"],
                env=offline_subprocess_env,
                cwd=project_dir,
            ),
            _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=project_dir),
        ]
        for channel in channels:
            assert self.PLANTED_SECRET not in channel.stdout
            assert self.PLANTED_SECRET not in channel.stderr

        # And it was moved rather than dropped, which is what makes the assertions above mean
        # something: the run read this value, wrote it under its new key, and never said it.
        assert self.PLANTED_SECRET in global_file.read_text(encoding="utf-8")
        assert load_toml_from_path(path=global_file)["custom_posthog"]["api_key"] == self.PLANTED_SECRET


class TestABootFailureCarriesThePendingMigration:
    """The third channel: a configuration that will not load says *why*, in fields and in prose.

    Boot tolerance already handles the case the ledger can explain — that machine boots, with a
    warning. What is left is the machine the ledger cannot explain, and until now all it got was
    pydantic's account of a key it had never heard of. It now also gets the scan: which of its
    files the walk would touch, what a `pipelex migrate` would carry forward, and what nobody but
    a person can resolve.

    **The structured block is the contract; the prose is presentation.** A machine consumer
    branches on `migration` being present, never on the wording — which is why both are asserted
    here, on the same run, through the real binary.
    """

    PLANTED_SECRET = "phc_L1VE_boot_error_key_that_must_never_be_rendered"

    def _break_the_configuration_with_a_secret(self, *, hermetic_home: Path) -> Path:
        """A root key no model knows, holding a value that looks exactly like a live credential.

        The unknown key is what breaks the boot *and* what the downgrade diagnosis reports; its
        value is what must never appear. Both halves in one key is deliberate — it means the
        diagnosis demonstrably read the value it declines to render.
        """
        config_file = hermetic_home / ".pipelex" / "pipelex.toml"
        planted = f'posthog_project_key = "{self.PLANTED_SECRET}"\n'
        config_file.write_text(planted + config_file.read_text(encoding="utf-8"), encoding="utf-8")
        return config_file

    def test_the_agent_boot_error_carries_the_config_domain_and_the_block(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        self._break_the_configuration_with_a_secret(hermetic_home=hermetic_home)

        boot = _boot(env=offline_subprocess_env, cwd=hermetic_home)

        assert boot.returncode != 0, "the scenario is worthless if this machine boots"
        # One envelope, and it has to be said out loud: `agent_error` leaves through `typer.Exit`,
        # which is a `RuntimeError` rather than a `SystemExit`, so a command boundary re-raising
        # only `SystemExit` caught it again and printed a second document after the first. Two
        # JSON documents on one stream is not JSON, and the block below would be unreadable.
        assert boot.stderr.count('"error": true') == 1, boot.stderr
        envelope: dict[str, Any] = json.loads(boot.stderr)
        assert envelope["error_type"] == "PipelexConfigError"
        assert envelope["error_domain"] == "config", "a new domain would route the agent hooks to BLOCK"

        block: dict[str, Any] = envelope["migration"]
        assert block["remedy"] == "pipelex migrate"
        assert block["needs_attention"] is True, "a key no entry explains is a person's to resolve"
        unexplained = [found for plan in block["plans"] for found in plan["unexplained"]]
        assert [found["path"] for found in unexplained] == ["posthog_project_key"]
        assert [plan["file_path"] for plan in block["plans"]] == [str(hermetic_home / ".pipelex" / "pipelex.toml")]

    def test_no_value_from_the_users_file_reaches_either_stream(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The contract's mechanical rule, on the channel that was waiting for this milestone.

        The diagnosis walked this document and reached the very key whose value is planted here —
        it names the key in the block above — so a rule that held only because nothing had read
        the value would be no rule at all.
        """
        config_file = self._break_the_configuration_with_a_secret(hermetic_home=hermetic_home)

        boot = _boot(env=offline_subprocess_env, cwd=hermetic_home)

        assert self.PLANTED_SECRET not in boot.stdout
        assert self.PLANTED_SECRET not in boot.stderr
        assert self.PLANTED_SECRET in config_file.read_text(encoding="utf-8"), "nothing was written, so the value is still there"

    def test_a_machine_the_ledger_can_explain_boots_instead_of_reporting(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The block's absence is a verdict too, and boot tolerance is why it is reachable.

        A stale file the ledger carries forward never reaches this error surface at all — it warns
        and boots. Without this test the block would look like the answer to staleness, when it is
        actually the answer to staleness the ledger *cannot* resolve.
        """
        project_dir, _, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)

        boot = _boot(env=offline_subprocess_env, cwd=project_dir)

        assert boot.returncode == 0, boot.stderr
        assert "migration" not in boot.stderr


class TestAStaleTelemetryFileIsMigratedNotReset:
    """Every surface that reports a stale `telemetry.toml` names the migration, not a fresh file.

    Until now each of them held its own hardcoded remedy — *config format has changed, run
    `pipelex init telemetry`* — written for exactly the shape the shipped ledger entry exists to
    carry forward. That command writes a new file: the PostHog key, the Langfuse credentials and
    the OTLP exporters a real machine has would all be gone.

    Two different machines are needed here, and the difference is boot tolerance. The `doctor`
    row is a filesystem probe, so it reports a file the ledger *can* explain — that machine boots
    fine, and the doctor is what says the change is not permanent yet. The error envelope needs a
    file that is old *and* wrong, because anything the ledger fully explains never reaches an
    error at all.
    """

    def test_the_agent_doctor_reports_the_finding_and_the_migrate_remedy(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, _, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)

        checked = _run(args=[str(PIPELEX_AGENT_BIN), "doctor", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)

        report: dict[str, Any] = json.loads(checked.stdout)
        telemetry: dict[str, Any] = report["checks"]["telemetry"]
        assert telemetry["healthy"] is False
        assert telemetry["finding"] == "out_of_date"
        actions: list[str] = report["recommended_actions"]
        assert any("pipelex migrate" in action for action in actions)
        assert not any("init telemetry" in action for action in actions), "this file is old, not broken"

    def test_a_telemetry_boot_failure_carries_the_block_in_one_envelope(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The other configuration surface that raises its own error type, on the same contract.

        Boot tolerance means a telemetry file has to be old *and* wrong to get here — flat, and
        carrying a key no telemetry schema ever had — which is exactly the machine the old
        remedy was worst for: it is migratable, and `pipelex init telemetry` would have answered
        it by writing a fresh file over the settings the migration keeps.
        """
        _, global_file, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)
        global_file.write_text(f"{_old_shape_telemetry_document()}\nnot_a_telemetry_setting = true\n", encoding="utf-8")

        boot = _boot(env=offline_subprocess_env, cwd=hermetic_home)

        assert boot.returncode != 0, "a file the ledger cannot fully explain still fails the boot"
        assert boot.stderr.count('"error": true') == 1, boot.stderr
        envelope: dict[str, Any] = json.loads(boot.stderr)
        assert envelope["error_type"] == "TelemetryConfigValidationError"
        assert envelope["error_domain"] == "config", "it comes from the class now, not the lookup table"
        assert envelope["migration"]["remedy"] == "pipelex migrate"
        assert "init telemetry" not in envelope["hint"]

    def test_the_human_doctor_says_migrate_and_never_offers_to_start_the_file_over(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, _, _ = _plant_a_stale_machine(hermetic_home=hermetic_home)

        checked = _run(args=[str(PIPELEX_BIN), "--no-logo", "doctor"], env=offline_subprocess_env, cwd=project_dir)

        # Both streams: the human doctor renders through a Rich console whose target the user's
        # own log configuration decides, so which one it lands on is not this test's business.
        printed = checked.stdout + checked.stderr
        assert "out of date" in printed, printed
        assert "pipelex migrate" in printed
        assert "pipelex init telemetry" not in printed
