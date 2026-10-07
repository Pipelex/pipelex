"""A machine a former release set up, through the installed binaries: refused at boot, cleaned up, booting again.

The home and a project's `.pipelex/` each carry what the v0.72 release wrote for the Pipelex Gateway and Pipelex
Manifold — its `backends.toml`, `routing_profiles.toml`, the two retired backend files, the Gateway's model lists and
`pipelex_service.toml`, copied from that release's wheel — laid over the current kit's inference tree, which stands in
for the per-backend files the inference-backend ledger carries forward on its own. That is the state every former user
is in, and each command a remedy names is run on it: the boot names `pipelex migrate` and `pipelex init`, `pipelex
migrate` and `pipelex-agent migrate` clean both directories so the machine boots, `pipelex doctor` names the cleanup
and `--fix` runs it, and `pipelex init` offers it before it asks where runs execute.

The boot probe is `pipelex-agent models`, the cheapest command that performs a full Pipelex boot.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - invokes the real pipelex binaries for E2E coverage
from pathlib import Path

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.former_release import detect_former_release
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, ROUTING_PROFILES_FILE_NAME
from tests.e2e.agent_cli.conftest import REPO_ROOT

PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
PIPELEX_AGENT_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex-agent"

V0_72_CONFIG_DIR = REPO_ROOT / "tests" / "data" / "migration" / "former_release" / "v0_72"
V0_72_CLEANED_DIR = REPO_ROOT / "tests" / "data" / "migration" / "former_release" / "v0_72_cleaned"

PROJECT_DIR_NAME = "workspace"

# The files the cleanup touches in one v0.72 directory, rewritten or removed.
V0_72_FILES_PER_DIRECTORY = len(detect_former_release(config_dir=V0_72_CONFIG_DIR).file_paths)

# A model table whose key the inference-backend ledger renames.
MIGRATABLE_MODEL_TABLE = '\n["gpt-4o"]\nprompting_target = "openai"\n'


def _plant_a_former_release_machine(*, hermetic_home: Path) -> tuple[Path, Path, Path]:
    """The v0.72 files over the kit, in the home `hermetic_home` seeded and in a project's `.pipelex/` beside it.

    Returns the project directory, the home configuration directory and the project's configuration directory.
    """
    home_config_dir = hermetic_home / ".pipelex"
    shutil.copytree(V0_72_CONFIG_DIR, home_config_dir, dirs_exist_ok=True)
    project_dir = hermetic_home / PROJECT_DIR_NAME
    project_config_dir = project_dir / ".pipelex"
    # A whole configuration directory, as that release's `pipelex init` wrote one into a project.
    shutil.copytree(Path(str(get_kit_configs_dir())), project_config_dir)
    shutil.copytree(V0_72_CONFIG_DIR, project_config_dir, dirs_exist_ok=True)
    return project_dir, home_config_dir, project_config_dir


def _run(*, args: list[str], env: dict[str, str], cwd: Path, answers: str | None = None) -> subprocess.CompletedProcess[str]:
    # A wide terminal, so Rich never breaks a long temporary path across two lines. `answers` feeds the prompts: every
    # question these commands ask here defaults to yes, so bare newlines accept each one in turn.
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
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
    return _run(args=[str(PIPELEX_AGENT_BIN), "models", "--format", "json"], env=env, cwd=cwd)


def _assert_cleaned(*, config_dirs: tuple[Path, ...]) -> None:
    for config_dir in config_dirs:
        assert detect_former_release(config_dir=config_dir).is_clean, f"something a former release left is still in {config_dir}"


class TestAFormerReleaseMachine:
    def test_the_boot_is_refused_with_the_one_error_naming_both_remedies(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        project_dir, _, _ = _plant_a_former_release_machine(hermetic_home=hermetic_home)

        booted = _boot(env=offline_subprocess_env, cwd=project_dir)

        assert booted.returncode != 0
        output = booted.stdout + booted.stderr
        assert "FormerReleaseConfigError" in output, output
        assert "pipelex migrate" in output
        assert "pipelex init" in output
        envelope = json.loads(booted.stderr)
        assert envelope["error_type"] == "FormerReleaseConfigError"
        assert "pipelex-agent migrate --dry-run --format json" in envelope["hint"], "an agent is handed the loop it can run"

    def test_pipelex_migrate_cleans_both_directories_and_the_machine_boots(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        project_dir, home_config_dir, project_config_dir = _plant_a_former_release_machine(hermetic_home=hermetic_home)

        migrated = _run(args=[str(PIPELEX_BIN), "--no-logo", "migrate", "--yes"], env=offline_subprocess_env, cwd=project_dir)

        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        report = migrated.stdout + migrated.stderr
        assert f"Cleaned up {2 * V0_72_FILES_PER_DIRECTORY} file(s) a former release left" in report
        _assert_cleaned(config_dirs=(home_config_dir, project_config_dir))
        for name in (BACKENDS_FILE_NAME, ROUTING_PROFILES_FILE_NAME):
            golden = (V0_72_CLEANED_DIR / INFERENCE_DIR_NAME / name).read_bytes()
            assert (home_config_dir / INFERENCE_DIR_NAME / name).read_bytes() == golden
            assert (project_config_dir / INFERENCE_DIR_NAME / name).read_bytes() == golden
        booted = _boot(env=offline_subprocess_env, cwd=project_dir)
        assert booted.returncode == 0, booted.stdout + booted.stderr

    def test_the_agent_loop_plans_the_cleanup_then_applies_it_and_the_machine_boots(
        self, hermetic_home: Path, offline_subprocess_env: dict[str, str]
    ) -> None:
        project_dir, home_config_dir, project_config_dir = _plant_a_former_release_machine(hermetic_home=hermetic_home)
        # A key the ledger would carry forward, in a file the cleanup removes: the replay never walks it.
        gateway_file = home_config_dir / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "pipelex_gateway.toml"
        with gateway_file.open("a", encoding="utf-8") as stream:
            stream.write(MIGRATABLE_MODEL_TABLE)

        planned = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--dry-run", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)

        assert planned.returncode == 0, planned.stdout + planned.stderr
        plan = json.loads(planned.stdout)
        assert plan["applied"] is False
        assert plan["is_clean"] is False
        assert plan["needs_attention"] is False
        assert plan["summary"]["former_release_files"] == 2 * V0_72_FILES_PER_DIRECTORY
        assert {file["action"] for file in plan["former_release"]["files"]} == {"rewrite", "remove"}
        assert str(gateway_file) not in {migration_plan["file_path"] for migration_plan in plan["plans"]}
        assert not detect_former_release(config_dir=home_config_dir).is_clean, "a dry run writes nothing"

        applied = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)

        assert applied.returncode == 0, applied.stdout + applied.stderr
        result = json.loads(applied.stdout)
        assert result["summary"]["former_release_files_cleaned"] == 2 * V0_72_FILES_PER_DIRECTORY
        assert all(file["backup_path"] for file in result["former_release"]["files"])
        assert result["former_release"]["still_blocking"] == []
        _assert_cleaned(config_dirs=(home_config_dir, project_config_dir))
        booted = _boot(env=offline_subprocess_env, cwd=project_dir)
        assert booted.returncode == 0, booted.stdout + booted.stderr

        again = _run(args=[str(PIPELEX_AGENT_BIN), "migrate", "--yes", "--format", "json"], env=offline_subprocess_env, cwd=project_dir)
        assert json.loads(again.stdout)["former_release"]["is_clean"] is True

    def test_pipelex_doctor_names_the_cleanup_and_fix_runs_it(self, hermetic_home: Path, offline_subprocess_env: dict[str, str]) -> None:
        project_dir, home_config_dir, project_config_dir = _plant_a_former_release_machine(hermetic_home=hermetic_home)

        diagnosed = _run(args=[str(PIPELEX_BIN), "--no-logo", "doctor"], env=offline_subprocess_env, cwd=project_dir)

        assert diagnosed.returncode == 1, diagnosed.stdout + diagnosed.stderr
        report = diagnosed.stdout + diagnosed.stderr
        assert f"{home_config_dir / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME} — left by a former release" in report
        assert "Pipelex cannot start until it does" in report
        assert "Not checked: what a former release left" in report

        fixed = _run(args=[str(PIPELEX_BIN), "--no-logo", "doctor", "--fix"], env=offline_subprocess_env, cwd=project_dir, answers="\n" * 20)

        assert f"Cleaned up {2 * V0_72_FILES_PER_DIRECTORY} file(s) a former release left" in fixed.stdout + fixed.stderr
        _assert_cleaned(config_dirs=(home_config_dir, project_config_dir))

    def test_pipelex_init_cleans_up_on_yes_then_asks_where_runs_execute(
        self, hermetic_home: Path, offline_subprocess_env: dict[str, str], fresh_home_env: dict[str, str]
    ) -> None:
        project_dir, home_config_dir, project_config_dir = _plant_a_former_release_machine(hermetic_home=hermetic_home)
        # The hosted path with a key already set, as the hosted init tests take it: no sign-in, no editor touched.
        env = {
            **offline_subprocess_env,
            **{key: fresh_home_env[key] for key in ("PATH", "PIPELEX_API_KEY", "PIPELEX_BASE_URL", "PIPELEX_APP_URL")},
        }

        initialized = _run(args=[str(PIPELEX_BIN), "--no-logo", "init"], env=env, cwd=project_dir, answers="\n" * 30)

        assert initialized.returncode == 0, initialized.stdout + initialized.stderr
        transcript = initialized.stdout + initialized.stderr
        assert "Left by a former release" in transcript
        cleaned_at = transcript.index("Clean it up now?")
        assert transcript.index("Where should your runs execute?") > cleaned_at, "the cleanup comes before the setup question"
        _assert_cleaned(config_dirs=(home_config_dir, project_config_dir))
