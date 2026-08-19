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

**Two surfaces are planted here, and the second one is the whole main configuration.**
``telemetry-config`` is the small specimen — one flat document, nested — and it is what most of
this module runs on because it is cheap and it shipped first. ``pipelex-config@3``, the
configuration reshape, is the other size of thing: it renames the root tables of the file every
boot reads, so the machine it migrates is every existing installation. Its fixture is
``goldens/pipelex-config/defaults@1.toml`` — the packaged ``pipelex.toml`` as it stood at schema 1
— plus a hand-written project tier, and ``TestAPreReshapeMachine`` is where they meet the two
binaries.

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
from pipelex.migration.goldens import defaults_golden_path, pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.migration.surfaces import build_config_surface_registry
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, BACKENDS_FILE_NAME, INFERENCE_DIR_NAME
from pipelex.system.configuration.config_surface import (
    INFERENCE_BACKEND_CONFIG_SURFACE_ID,
    PIPELEX_CONFIG_SURFACE_ID,
    TELEMETRY_CONFIG_SURFACE_ID,
)
from pipelex.tools.misc.toml_utils import load_toml_from_path
from tests.e2e.agent_cli.conftest import REPO_ROOT

if TYPE_CHECKING:
    from pathlib import Path

PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
PIPELEX_AGENT_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex-agent"

PROJECT_DIR_NAME = "workspace"

# A tier file of the flat era, as a user would have written one: a couple of overrides on top of
# the global file, not the whole census the golden carries.
OLD_SHAPE_PROJECT_OVERRIDE = """\
# My project keeps telemetry quiet.
telemetry_mode = "off"
host = "https://project.example.invalid"
"""

# The same idea one surface up: a project tier of the pre-reshape era. Modelled on a real machine's
# `pipelex_override.toml` — its table headers, with every value invented, because a checked-in
# fixture must carry none of a person's. The handful of tables is deliberate and it is what makes
# this a fair specimen: each one leaves `[pipelex]` by a different route (two `move_key`s, the root
# rename, and a rename inside what that rename leaves behind), so a tier file exercises four of the
# entry's operation shapes without being a second census.
OLD_SHAPE_PROJECT_PIPELEX_OVERRIDE = """\
# This project keeps its own bucket and turns the logs up.
[pipelex.log_config]
default_log_level = "DEBUG"

[pipelex.log_config.package_log_levels]
pipelex = "DEBUG"

[pipelex.storage_config]
method = "s3"

[pipelex.storage_config.s3]
bucket_name = "example-project-bucket"
region = "eu-west-3"

[pipelex.builder_config]
default_output_dir = "build"
"""


# The templating section as schema 1 spells it, and as the release before it did. `#1104` renamed
# the section and its one key and dropped the per-target map, and the pre-history entry
# `pipelex-config@2` is what carries a file written before that. The pair is used to rewind
# `defaults@1.toml` one release further back — a text swap rather than a transcribed document, so
# that everything the reshape entry is about goes on being read live and only the half this is
# about is stated here. A swap that stopped matching would leave a fixture that is not old at all,
# which is why the planting asserts on the result.
TEMPLATING_SECTION_AT_SCHEMA_1 = """\
[pipelex.templating_config]
default_templating_style = { tag_style = "xml" }
"""

PROMPTING_SECTION_BEFORE_SCHEMA_1 = """\
[pipelex.prompting_config]
default_prompting_style = { tag_style = "xml" }

[pipelex.prompting_config.prompting_styles]
openai = { tag_style = "ticks" }
anthropic = { tag_style = "xml" }
mistral = { tag_style = "square_brackets" }
gemini = { tag_style = "xml" }
"""

# The key `#1104` deleted from the model-spec blueprint and from every backend file we ship, and a
# value no ledger sentence contains — so the reports can be searched for it, and finding it would be
# a value read from a user's file having reached a channel that must never carry one.
RETIRED_BACKEND_KEY = "prompting_target"
PLANTED_BACKEND_VALUE = "a_prompting_target_no_report_may_ever_render"

# How `stale_configuration_warning` opens. Matched in full rather than on a fragment: the same boot
# also prints a deck-staleness notice, and "out of date" appears in both.
STALE_CONFIGURATION_OPENING = "Your configuration is out of date"


def _old_shape_telemetry_document() -> str:
    """The flat pre-history document the shipped entry is about, read from the package."""
    path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
    return path.read_text(encoding="utf-8")


# The storage `uri_format` as schema 1 spelled it, and as the current models require it. The
# placeholder set narrowed without any path moving, so no ledger entry describes it — see the
# note inside the function below.
_STORAGE_URI_FORMAT_AT_SCHEMA_1 = '"{primary_id}/{secondary_id}/{hash}.{extension}"'
_STORAGE_URI_FORMAT_TODAY = '"{hash}.{extension}"'


def _pre_reshape_pipelex_config_document() -> str:
    """The whole main configuration in its pre-reshape shape, read from the package.

    `defaults@1.toml` is the packaged `pipelex.toml` as it stood at schema 1 — the document the
    reshape entry was authored against — so it names every path the entry touches and nothing it
    does not. Read live rather than transcribed here, for the same reason the telemetry fixture is:
    a transcribed one would eventually describe a shape the shipped ledger no longer migrates, and
    would go on passing.

    It is read at schema 1 by name and not at the version the reshape now starts from, which is one
    higher: the pre-history entry inserted below the reshape changed nothing in the models, so its
    reference document is a byte copy of this one. Naming the version where the document's shape was
    actually cut is the spelling that says what this is, rather than one inherited from a copy.

    One value is modernized on the way out, and it is not a shape change, which is why the ledger
    is silent about it and right to be. `uri_format`'s PLACEHOLDER SET narrowed —
    `{primary_id}`/`{secondary_id}` gave way to `{storage_scope}` — and a value domain narrowing
    with no path added, removed or moved is a *content* change, out of scope for a structural
    vocabulary (see `docs/migration-ledger.md`). The golden stays a true record of schema 1; what
    this fixture needs is a document that is pre-reshape in SHAPE, since the reshape is what it
    exercises, while still being one the current models will load. Left as-is, the planted machine
    fails `_assert_boots` before `migrate` is ever reached, and the reshape goes untested.
    """
    path = defaults_golden_path(migration_dir=packaged_migration_dir(), surface_id=PIPELEX_CONFIG_SURFACE_ID, schema_version=1)
    document = path.read_text(encoding="utf-8")
    modernized = document.replace(_STORAGE_URI_FORMAT_AT_SCHEMA_1, _STORAGE_URI_FORMAT_TODAY)
    if modernized == document:
        msg = (
            "the schema-1 storage uri_format is no longer spelled the way this fixture modernizes:\n"
            f"{_STORAGE_URI_FORMAT_AT_SCHEMA_1}\n"
            "If the placeholder set changed again, update the two constants above — a silent no-op here "
            "plants a document that cannot boot, and the reshape stops being tested."
        )
        raise AssertionError(msg)
    return modernized


def _todays_pipelex_config_document() -> dict[str, Any]:
    """What the package's own `pipelex.toml` says now — the shape a migration has to land on.

    Read through the surface rather than by path, so this tracks wherever the packaged document
    lives, and read as the live file rather than as the head golden: that golden is a snapshot of
    this, and comparing against the snapshot would leave a gap exactly the width of a stale one.
    """
    registry = build_config_surface_registry()
    return registry.surface_for_id(surface_id=PIPELEX_CONFIG_SURFACE_ID).read_defaults_document()


def _project_config_dir(*, hermetic_home: Path) -> Path:
    """The `.pipelex/` of a project rooted inside the hermetic HOME, created if it is not there.

    `exist_ok`, because a machine can be behind on more than one surface at once and the plantings
    that make it so are separate functions that both need this directory.
    """
    config_dir = hermetic_home / PROJECT_DIR_NAME / ".pipelex"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


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

    project_file = _project_config_dir(hermetic_home=hermetic_home) / "telemetry_override.toml"
    project_file.write_text(OLD_SHAPE_PROJECT_OVERRIDE, encoding="utf-8")
    return hermetic_home / PROJECT_DIR_NAME, global_file, project_file


def _plant_a_pre_reshape_machine(*, hermetic_home: Path) -> tuple[Path, Path, Path]:
    """The same two tiers, one surface up: a main configuration written before the reshape.

    The global file **replaces** what `hermetic_home` seeded there, which is the current kit
    template — a machine that had already been migrated would prove nothing. The project tier is a
    `pipelex_override.toml`, claimed by the surface's `pipelex_*.toml` glob and merged by the
    loader, so a run that reached only the base file would come back visibly short.

    Returns the project directory, the global file and the project file.
    """
    global_file = hermetic_home / ".pipelex" / "pipelex.toml"
    global_file.write_text(_pre_reshape_pipelex_config_document(), encoding="utf-8")

    project_file = _project_config_dir(hermetic_home=hermetic_home) / "pipelex_override.toml"
    project_file.write_text(OLD_SHAPE_PROJECT_PIPELEX_OVERRIDE, encoding="utf-8")
    return hermetic_home / PROJECT_DIR_NAME, global_file, project_file


def _plant_a_pre_prompting_style_machine(*, hermetic_home: Path) -> tuple[Path, Path]:
    """One release further back than the machine above: a file that still names prompting styles.

    Two entries have to run on it, in order, and the order is the whole point — the first addresses
    `pipelex.prompting_config` at the spelling it had *before* the reshape renames `[pipelex]`, so a
    file that met only the reshape would arrive at `[interpreter.prompting_config]`, which nothing
    reads and the model refuses.

    Only the global tier is planted. The project tier beside it is the reshape's specimen and it has
    nothing to say about prompting styles; a second file carrying the same two tables would prove the
    same thing twice.

    Returns the project directory and the global file.
    """
    at_schema_1 = _pre_reshape_pipelex_config_document()
    older = at_schema_1.replace(TEMPLATING_SECTION_AT_SCHEMA_1, PROMPTING_SECTION_BEFORE_SCHEMA_1)
    if older == at_schema_1:
        msg = f"the schema-1 templating section is no longer spelled the way this fixture rewinds:\n{TEMPLATING_SECTION_AT_SCHEMA_1}"
        raise AssertionError(msg)

    global_file = hermetic_home / ".pipelex" / "pipelex.toml"
    global_file.write_text(older, encoding="utf-8")

    _project_config_dir(hermetic_home=hermetic_home)
    return hermetic_home / PROJECT_DIR_NAME, global_file


def _backends_dir(*, hermetic_home: Path) -> Path:
    return hermetic_home / ".pipelex" / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME


def _plant_a_stale_backend_directory(*, hermetic_home: Path) -> tuple[Path, Path]:
    """The third surface's machine: backend definitions written before `#1104` deleted a key.

    `hermetic_home` seeds `inference/backends/` from the kit, which is exactly what `pipelex init`
    puts on a machine — so ageing it is a matter of putting `prompting_target` back where an
    installation from before this release still has it: in one file's `[defaults]`, where it breaks
    every model of that file at once, and on another file's model tables, where each is rejected by
    name. Two files rather than one because the surface claims a directory, and a run that reached
    only the first would come back visibly short.

    The value planted is a marker no ledger sentence contains, which is what lets the reports be
    checked for it. Both plantings raise if their anchor is gone, so a kit file that stops carrying
    it turns this red rather than quietly ageing nothing.

    Returns the two stale files.
    """
    backends_dir = _backends_dir(hermetic_home=hermetic_home)
    openai_file = backends_dir / "openai.toml"
    portkey_file = backends_dir / "portkey.toml"

    in_defaults = openai_file.read_text(encoding="utf-8")
    aged_defaults = in_defaults.replace("[defaults]\n", f'[defaults]\n{RETIRED_BACKEND_KEY} = "{PLANTED_BACKEND_VALUE}"\n', 1)
    if aged_defaults == in_defaults:
        msg = f"the kit's openai.toml no longer has a [defaults] block to age: {openai_file}"
        raise AssertionError(msg)
    openai_file.write_text(aged_defaults, encoding="utf-8")

    per_model = portkey_file.read_text(encoding="utf-8")
    aged_models = per_model
    for table_header in ("[gpt-4o]", '["gemini-2.5-pro"]'):
        aged_models = aged_models.replace(f"{table_header}\n", f'{table_header}\n{RETIRED_BACKEND_KEY} = "{PLANTED_BACKEND_VALUE}"\n', 1)
    if aged_models == per_model:
        msg = f"the kit's portkey.toml no longer has the model tables this fixture ages: {portkey_file}"
        raise AssertionError(msg)
    portkey_file.write_text(aged_models, encoding="utf-8")

    return openai_file, portkey_file


def _run(*, args: list[str], env: dict[str, str], cwd: Path, answers: str | None = None) -> subprocess.CompletedProcess[str]:
    # A wide terminal, because the human CLI renders through Rich and Rich wraps at the console
    # width. A temp-directory path is long enough to be broken across two lines at the default 80,
    # which would make these assertions fail for a reason that has nothing to do with migration.
    #
    # `answers` feeds an interactive command's prompts. Every confirmation the doctor asks defaults
    # to yes, so a run of bare newlines accepts each one in turn without this having to know how
    # many there will be or what order they come in.
    return subprocess.run(  # noqa: S603
        args,
        env={**env, "COLUMNS": "400"},
        cwd=str(cwd),
        input=answers,
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


class TestAPreReshapeMachine:
    """The machine this release actually meets: a main configuration written before the reshape.

    Everything above is planted on `telemetry-config`, whose entry nests one flat document — a
    small change, and one that shipped before the reshape did. `pipelex-config@3` is the other
    size of thing. It renames the root tables of the file every boot reads, so the machine it
    migrates is not a corner case but every installation that predates this release, and the two
    tiers planted here are the two a real one has: the global `~/.pipelex/pipelex.toml` an install
    left behind, and a project's `pipelex_override.toml` beside it.

    Until this class the entry was proved by the engine's own goldens and by nothing else. What is
    added is the rest of the chain — the walk, the filesystem, the backup, the binary a person
    types — and the property that only the whole chain can show: a boot that carries the old shape
    forward in memory, a command that then writes it, and a boot that has nothing left to carry.
    """

    def test_the_human_command_carries_a_pre_reshape_machine_onto_todays_shape(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The whole loop through `pipelex migrate`, with the strong assertion on the global file.

        Migrated, it says exactly what the package's own `pipelex.toml` says today.
        `make check-migration-schemas` already proves the *engine* turns the reference document the
        reshape starts from into the one it lands on; what is proved here is that the *command*
        does — walking two directories,
        reading a user's file off a disk, writing it back and leaving the original beside it —
        which no golden can show.

        Semantically, not byte for byte, and the entry's own guidance says why: a moved section may
        land at the end of the migrated file rather than where it was, and a banner comment
        introducing one stays behind. What the migration keeps is settings, not layout.
        """
        project_dir, global_file, project_file = _plant_a_pre_reshape_machine(hermetic_home=hermetic_home)
        originals = {path: path.read_text(encoding="utf-8") for path in (global_file, project_file)}

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

        migrated = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=project_dir)

        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        report = migrated.stdout + migrated.stderr
        assert str(global_file) in report
        assert str(project_file) in report

        assert load_toml_from_path(path=global_file) == _todays_pipelex_config_document()
        # The tier keeps its four settings and nothing else — a migration that had quietly folded
        # the package defaults into a user's override would satisfy the assertion above and ruin
        # the layering, since an override is read as "only these, on top of whatever is beneath".
        assert load_toml_from_path(path=project_file) == {
            "runtime": {
                "log": {"default_log_level": "DEBUG", "package_log_levels": {"pipelex": "DEBUG"}},
                "storage": {"method": "s3", "s3": {"bucket_name": "example-project-bucket", "region": "eu-west-3"}},
            },
            "interpreter": {"builder": {"default_output_dir": "build"}},
        }

        for path, original in originals.items():
            backups = existing_backups_of(path=path)
            assert len(backups) == 1, f"expected exactly one backup of {path}, found {backups}"
            assert backups[0].read_text(encoding="utf-8") == original

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

    def test_the_agent_loop_plans_the_reshape_then_applies_it(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The same machine through the other binary, where the plan is a document rather than prose.

        The entry is named per file rather than once for the run, and both files name it: a tier
        migrates on its own terms, and a plan that summarized the run would leave a consumer unable
        to tell which of its files a given step was about.
        """
        project_dir, global_file, project_file = _plant_a_pre_reshape_machine(hermetic_home=hermetic_home)

        planned = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=project_dir,
        )
        assert planned.returncode == 0, planned.stderr
        plan: dict[str, Any] = json.loads(planned.stdout)

        assert plan["applied"] is False
        assert plan["is_clean"] is False
        assert plan["needs_attention"] is False, "every path in a pre-reshape file is one the entry explains"
        assert plan["summary"]["files_changed"] == 2
        assert plan["summary"]["files_written"] == 0
        stepped = {plan_dict["file_path"]: [step["title"] for step in plan_dict["steps"]] for plan_dict in plan["plans"] if plan_dict["steps"]}
        assert stepped == {
            str(global_file): ["The configuration reshape: one scheme for the root"],
            str(project_file): ["The configuration reshape: one scheme for the root"],
        }
        assert existing_backups_of(path=global_file) == [], "a plan is not a write"

        applied = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)
        assert applied.returncode == 0, applied.stderr
        outcome: dict[str, Any] = json.loads(applied.stdout)

        assert outcome["applied"] is True
        assert outcome["summary"]["files_written"] == 2
        written = {plan_dict["file_path"] for plan_dict in outcome["plans"] if plan_dict["was_written"]}
        assert written == {str(global_file), str(project_file)}

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

    def test_one_run_migrates_every_surface_the_machine_is_behind_on(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """A machine upgrading across this release is behind on two surfaces, not one.

        Nothing else in this module puts two ledgers in one run, and the run is where they could
        interfere: the walk claims each file for exactly one surface, and a file claimed for the
        wrong one would either be reported clean or be handed a ledger with nothing to say about
        it. Four files written, from two directories, under two entries.
        """
        _plant_a_stale_machine(hermetic_home=hermetic_home)
        project_dir, _, _ = _plant_a_pre_reshape_machine(hermetic_home=hermetic_home)

        applied = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)

        assert applied.returncode == 0, applied.stderr
        outcome: dict[str, Any] = json.loads(applied.stdout)
        assert outcome["summary"]["files_written"] == 4
        assert outcome["needs_attention"] is False

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

        settled = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=project_dir,
        )
        assert json.loads(settled.stdout)["is_clean"] is True

    def test_no_value_from_a_pre_reshape_file_is_rendered_while_it_is_moved(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The contract's mechanical rule again, on the entry that moves the most.

        The planted value is a bucket name rather than a credential, because the main configuration
        holds no credentials — secrets reach it through the environment. It is still exactly what
        must not leave the machine: private infrastructure, in the file a person pastes into an
        issue when a boot goes wrong. It rides a `move_key` the reshape performs, so the run
        demonstrably read it, wrote it under its new address, and never said it.
        """
        planted = "s3-prod-eu-pipelex-artifacts-must-never-be-rendered"
        project_dir, _, project_file = _plant_a_pre_reshape_machine(hermetic_home=hermetic_home)
        project_file.write_text(OLD_SHAPE_PROJECT_PIPELEX_OVERRIDE.replace("example-project-bucket", planted), encoding="utf-8")

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
            assert planted not in channel.stdout
            assert planted not in channel.stderr

        assert load_toml_from_path(path=project_file)["runtime"]["storage"]["s3"]["bucket_name"] == planted

    def test_a_pre_reshape_file_the_entry_only_half_explains_reports_both_halves(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """Old *and* wrong: the boot fails, and the block says which part the command can take.

        This is the machine a person actually writes to support about, and it is the one where the
        two halves of the report have to coexist — the reshape is pending on this file *and* it
        holds a key no entry explains. A block that reported only the second would read as "your
        configuration is broken", when most of what is wrong with it is a command away.
        """
        planted = "phc_L1VE_pre_reshape_key_that_must_never_be_rendered"
        _plant_a_pre_reshape_machine(hermetic_home=hermetic_home)
        global_file = hermetic_home / ".pipelex" / "pipelex.toml"
        # At the top of the document, so the key lands at the root rather than inside whichever
        # table happens to be last — and the root is where no ledger operation would remove it.
        global_file.write_text(f'posthog_project_key = "{planted}"\n{global_file.read_text(encoding="utf-8")}', encoding="utf-8")

        boot = _boot(env=offline_subprocess_env, cwd=hermetic_home)

        assert boot.returncode != 0, "a file the ledger cannot fully explain still fails the boot"
        assert boot.stderr.count('"error": true') == 1, boot.stderr
        envelope: dict[str, Any] = json.loads(boot.stderr)
        assert envelope["error_type"] == "PipelexConfigError"
        assert envelope["error_domain"] == "config"

        block: dict[str, Any] = envelope["migration"]
        assert block["remedy"] == "pipelex migrate"
        assert block["needs_attention"] is True
        assert [step["title"] for plan in block["plans"] for step in plan["steps"]] == ["The configuration reshape: one scheme for the root"]
        assert [found["path"] for plan in block["plans"] for found in plan["unexplained"]] == ["posthog_project_key"]

        assert planted not in boot.stdout
        assert planted not in boot.stderr
        assert planted in global_file.read_text(encoding="utf-8"), "nothing was written, so the value is still there"


class TestAPrePromptingStyleMachine:
    """Two entries on one file, in the order that makes the first one's paths exist.

    `pipelex-config@2` is the other half of the templating change: `#1104` deleted
    `prompting_config` from the model and from the packaged file, and — because `pipelex init` never
    overwrites — left it behind on every machine that had one. It is a *pre-history* entry inserted
    below the reshape rather than appended above it, because it addresses `pipelex.prompting_config`,
    the spelling that only exists while `[pipelex]` is still called `[pipelex]`. Appended after the
    reshape it would find nothing, and the file would come out of the run carrying
    `[interpreter.prompting_config]` — a table the model refuses, on a machine the tool has just
    reported as migrated.

    So the property here is not "the entry works" but "the two entries compose": one machine, one
    run, and a file that arrives at exactly what the package ships today.
    """

    def test_the_human_command_carries_a_pre_prompting_style_machine_onto_todays_shape(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        project_dir, global_file = _plant_a_pre_prompting_style_machine(hermetic_home=hermetic_home)
        original = global_file.read_text(encoding="utf-8")
        planted: dict[str, Any] = load_toml_from_path(path=global_file)
        assert "prompting_config" in planted["pipelex"], "the fixture has to start out old, or nothing below is measured"

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

        migrated = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=project_dir)

        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        assert str(global_file) in migrated.stdout + migrated.stderr

        # The whole document, against the live packaged one: the tuned per-target map is gone, the
        # default it sat beside travels to where the reshape puts templating, and nothing else about
        # a file that crossed two entries in one run came out different.
        assert load_toml_from_path(path=global_file) == _todays_pipelex_config_document()

        backups = existing_backups_of(path=global_file)
        assert len(backups) == 1, f"expected exactly one backup of {global_file}, found {backups}"
        assert backups[0].read_text(encoding="utf-8") == original

        _assert_boots(env=offline_subprocess_env, cwd=project_dir)

    def test_the_agent_loop_names_both_entries_for_the_one_file(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """A plan that named only the reshape would be a plan a consumer could not act on.

        The order of the steps is the order they ran in, and it is the load-bearing half: a reader
        of this plan has to be able to see that the prompting section was dealt with while it was
        still under `[pipelex]`.
        """
        project_dir, global_file = _plant_a_pre_prompting_style_machine(hermetic_home=hermetic_home)

        planned = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=project_dir,
        )
        assert planned.returncode == 0, planned.stderr
        plan: dict[str, Any] = json.loads(planned.stdout)

        assert plan["is_clean"] is False
        assert plan["needs_attention"] is False, "every path of a pre-prompting-style file is one the two entries explain"
        stepped = {plan_dict["file_path"]: [step["title"] for step in plan_dict["steps"]] for plan_dict in plan["plans"] if plan_dict["steps"]}
        assert stepped == {
            str(global_file): [
                "Prompting styles become a templating default",
                "The configuration reshape: one scheme for the root",
            ]
        }


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


class TestAStaleBackendDirectory:
    """The fourth surface, end to end: `inference/backends/*.toml` on a machine set up before `#1104`.

    Everything else in this module is planted on a file that sits *directly* in a configuration
    directory. These files do not: they are the reason the walk learned to enter a subdirectory at
    all, and the reason a file is claimed by `(directory, name)` rather than by name — the kit ships
    a `pipelex_gateway.toml` in there, which the main configuration's `pipelex_*.toml` glob would
    otherwise have claimed. It is present here for that reason, untouched, and the assertions say so.

    What a boot *says* is not asserted here and cannot be: the probe is `pipelex-agent`, which cuts
    logging off process-wide as its first act. The warning is asserted through the human binary
    below, and per surface in `tests/unit/pipelex/cogt/model_backends/test_backend_boot_tolerance.py`.
    """

    def _untouched_neighbours(self, *, hermetic_home: Path, migrated: tuple[Path, ...]) -> dict[Path, bytes]:
        """Everything in and beside the directory that no migration may rewrite.

        Excluded by name rather than by extension, and the difference is the whole point of this
        class: the kit ships `pipelex_gateway.toml` in this directory, which the main configuration's
        `pipelex_*.toml` glob would claim by name alone, so it is the one file a walk that forgot
        about directories would rewrite. An extension filter dropped it — and every other `.toml` in
        here — out of the snapshot, leaving the class's own claim unasserted. Only the files the
        fixture aged are excluded now. `inference/backends.toml` is added back from one level up,
        which is a different claim entirely: it is a table per backend rather than a table per model,
        and `#1104` never touched it.

        The snapshot is taken before the migration runs, so the `.bak` siblings it writes never enter
        it and cannot break the comparison.
        """
        backends_dir = _backends_dir(hermetic_home=hermetic_home)
        neighbours = [path for path in sorted(backends_dir.iterdir()) if path not in migrated]
        neighbours.append(hermetic_home / ".pipelex" / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME)
        return {path: path.read_bytes() for path in neighbours}

    def test_the_human_command_repairs_the_directory_in_place_and_leaves_one_backup_per_file(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        openai_file, portkey_file = _plant_a_stale_backend_directory(hermetic_home=hermetic_home)
        originals = {path: path.read_text(encoding="utf-8") for path in (openai_file, portkey_file)}
        neighbours = self._untouched_neighbours(hermetic_home=hermetic_home, migrated=(openai_file, portkey_file))

        _assert_boots(env=offline_subprocess_env, cwd=hermetic_home)

        migrated = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=hermetic_home)

        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        report = migrated.stdout + migrated.stderr
        assert str(openai_file) in report
        assert str(portkey_file) in report

        for path, original in originals.items():
            assert RETIRED_BACKEND_KEY not in path.read_text(encoding="utf-8"), f"{path} still carries the retired key"
            backups = existing_backups_of(path=path)
            assert len(backups) == 1, f"expected exactly one backup of {path}, found {backups}"
            assert backups[0].read_text(encoding="utf-8") == original
        assert {path: path.read_bytes() for path in neighbours} == neighbours

        _assert_boots(env=offline_subprocess_env, cwd=hermetic_home)

    def test_a_second_run_writes_nothing_and_leaves_no_second_backup(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """Replay neutrality over a directory, which is where it is easiest to get wrong.

        Every file of the surface is replayed on every run — twenty of them here — so a run that
        was not neutral would show up as twenty backups of files nothing was ever wrong with.
        """
        openai_file, portkey_file = _plant_a_stale_backend_directory(hermetic_home=hermetic_home)

        first = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=hermetic_home)
        assert first.returncode == 0, first.stderr
        assert json.loads(first.stdout)["summary"]["files_written"] == 2

        after_first = {path: path.read_bytes() for path in sorted(_backends_dir(hermetic_home=hermetic_home).iterdir())}

        second = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=hermetic_home)
        assert second.returncode == 0, second.stderr
        outcome: dict[str, Any] = json.loads(second.stdout)
        assert outcome["is_clean"] is True
        assert outcome["summary"]["files_written"] == 0
        assert {path: path.read_bytes() for path in sorted(_backends_dir(hermetic_home=hermetic_home).iterdir())} == after_first
        for path in (openai_file, portkey_file):
            assert len(existing_backups_of(path=path)) == 1

    def test_the_agent_loop_names_both_files_the_entry_and_its_operation(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        openai_file, portkey_file = _plant_a_stale_backend_directory(hermetic_home=hermetic_home)
        original = openai_file.read_text(encoding="utf-8")

        planned = _run(
            args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
            env=offline_subprocess_env,
            cwd=hermetic_home,
        )

        assert planned.returncode == 0, planned.stderr
        plan: dict[str, Any] = json.loads(planned.stdout)
        assert plan["applied"] is False
        assert plan["needs_attention"] is False, "the ledger explains every key these files carry"
        assert plan["summary"]["files_changed"] == 2

        changed = {plan_dict["file_path"]: plan_dict for plan_dict in plan["plans"] if plan_dict["steps"]}
        assert set(changed) == {str(openai_file), str(portkey_file)}
        for plan_dict in changed.values():
            assert [step["entry_id"] for step in plan_dict["steps"]] == [f"{INFERENCE_BACKEND_CONFIG_SURFACE_ID}@2"]
            ops = [op for step in plan_dict["steps"] for op in step["applied_ops"]]
            assert [(op["kind"], op["key"]) for op in ops] == [("delete_key", RETIRED_BACKEND_KEY)]

        assert openai_file.read_text(encoding="utf-8") == original, "a plan is not a write"
        assert existing_backups_of(path=openai_file) == []

    def test_no_channel_renders_the_value_the_files_carry(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The standing rule, on the surface whose files hold a value per model rather than per key.

        The operation is a delete, so what a report *could* leak is the value it is deleting — which
        is why the fixture plants a marker rather than a plausible-looking one: an assertion that
        passed because the value happened to look like ledger text would prove nothing.
        """
        _plant_a_stale_backend_directory(hermetic_home=hermetic_home)

        channels = [
            _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--dry-run"], env=offline_subprocess_env, cwd=hermetic_home),
            _run(
                args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"],
                env=offline_subprocess_env,
                cwd=hermetic_home,
            ),
            _run(
                args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "markdown"],
                env=offline_subprocess_env,
                cwd=hermetic_home,
            ),
            _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=hermetic_home),
        ]
        for channel in channels:
            assert PLANTED_BACKEND_VALUE not in channel.stdout
            assert PLANTED_BACKEND_VALUE not in channel.stderr

    def test_the_doctor_row_names_the_backend_files_and_goes_quiet_once_they_are_migrated(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The one channel a machine has for a pending migration, now that a stale directory boots."""
        openai_file, portkey_file = _plant_a_stale_backend_directory(hermetic_home=hermetic_home)

        checked = _run(args=[str(PIPELEX_AGENT_BIN), "doctor", "--format", "json"], env=offline_subprocess_env, cwd=hermetic_home)
        row: dict[str, Any] = json.loads(checked.stdout)["checks"]["pending_migrations"]

        assert row["finding"] == "pending"
        assert sorted(row["migratable_files"]) == sorted([str(openai_file), str(portkey_file)])

        _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=hermetic_home)

        rechecked = _run(args=[str(PIPELEX_AGENT_BIN), "doctor", "--format", "json"], env=offline_subprocess_env, cwd=hermetic_home)
        assert json.loads(rechecked.stdout)["checks"]["pending_migrations"]["finding"] == "up_to_date"

    def test_a_person_booting_the_stale_machine_is_told_and_stops_being_told_once_it_is_migrated(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """The warning itself, through the human binary — the half `pipelex-agent` cannot show.

        `show backends` is the cheapest human command that performs the inference half of a boot,
        which is where the backend library is loaded and where a directory the ledger carried
        forward is reported. The second run is what makes it a warning about staleness rather than
        a line the command always prints.
        """
        openai_file, portkey_file = _plant_a_stale_backend_directory(hermetic_home=hermetic_home)

        booted = _run(args=[str(PIPELEX_BIN), "--no-logo", "show", "backends"], env=offline_subprocess_env, cwd=hermetic_home)

        assert booted.returncode == 0, booted.stdout + booted.stderr
        printed = booted.stdout + booted.stderr
        # The warning's own opening words, not a phrase it shares with the deck-staleness notice
        # this same boot prints — "out of date" alone would match either of them.
        assert STALE_CONFIGURATION_OPENING in printed
        assert "pipelex migrate" in printed
        assert PLANTED_BACKEND_VALUE not in printed
        for path in (openai_file, portkey_file):
            assert existing_backups_of(path=path) == [], "a boot writes nothing"

        _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=hermetic_home)

        rebooted = _run(args=[str(PIPELEX_BIN), "--no-logo", "show", "backends"], env=offline_subprocess_env, cwd=hermetic_home)
        assert rebooted.returncode == 0, rebooted.stdout + rebooted.stderr
        assert STALE_CONFIGURATION_OPENING not in rebooted.stdout + rebooted.stderr


class TestTheDoctorReportsAndRepairsAStaleMachine:
    """The row that tells a machine a migration is pending, and the fix mode that runs it.

    A boot never says this: a stale configuration the ledger can explain boots with a warning, and
    `pipelex-agent` cuts logging off process-wide as its first act so nothing can emit one. Asking
    is the only channel a machine has, which is what makes this row load-bearing rather than
    convenient.
    """

    def test_the_agent_doctor_names_every_file_a_migration_would_touch_and_writes_nothing(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """Both directories, because both are what the command it names would rewrite.

        The row is scoped to no directory at all, unlike every other check here — `pipelex migrate`
        has no `--global`. And it is a report: the files it names are exactly as it found them.
        """
        project_dir, global_file, project_file = _plant_a_stale_machine(hermetic_home=hermetic_home)
        before = {path: path.read_text(encoding="utf-8") for path in (global_file, project_file)}

        checked = _run(args=[str(PIPELEX_AGENT_BIN), "doctor", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)

        report: dict[str, Any] = json.loads(checked.stdout)
        row: dict[str, Any] = report["checks"]["pending_migrations"]
        assert row["healthy"] is False
        assert row["finding"] == "pending"
        assert sorted(row["migratable_files"]) == sorted([str(global_file), str(project_file)])
        assert any("pipelex migrate" in action for action in report["recommended_actions"])
        for path, text in before.items():
            assert path.read_text(encoding="utf-8") == text, "a health report writes nothing"
            assert existing_backups_of(path=path) == []

    def test_fix_mode_runs_the_migration_and_keeps_what_was_in_the_files(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """`--fix` offers the command rather than merely naming it, and it is the same command.

        Every confirmation the doctor asks defaults to yes, so bare newlines accept whatever it
        offers — which is deliberate here: the assertion is about the files, and it holds however
        many other fixes this machine happens to be offered alongside the migration.
        """
        project_dir, global_file, project_file = _plant_a_stale_machine(hermetic_home=hermetic_home)

        _run(args=[str(PIPELEX_BIN), "--no-logo", "doctor", "--fix"], env=offline_subprocess_env, cwd=project_dir, answers="\n" * 8)

        for path in (global_file, project_file):
            migrated = load_toml_from_path(path)
            assert "custom_posthog" in migrated, f"{path} was not migrated"
            assert len(existing_backups_of(path=path)) == 1, "the original is kept beside it"
        # The settings the old destructive remedy would have discarded are still there.
        assert load_toml_from_path(project_file)["custom_posthog"]["endpoint"] == "https://project.example.invalid"

        checked = _run(args=[str(PIPELEX_AGENT_BIN), "doctor", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)
        assert json.loads(checked.stdout)["checks"]["pending_migrations"]["finding"] == "up_to_date"
