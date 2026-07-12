"""Unit tests for `pipelex-dev drift ack`: verify gating, reviewer resolution, index semantics."""

from __future__ import annotations

import shlex
import sys
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from pipelex.cli.dev_cli.commands.drift.drift_cmd import drift_ack_cmd, drift_app, drift_check_cmd
from pipelex.cli.dev_cli.commands.drift.exceptions import DriftAckError, DriftGitError
from pipelex.cli.dev_cli.commands.drift.git_adapter import read_staged_files
from pipelex.cli.dev_cli.commands.drift.models import ack_file_path, load_all_acks

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from rich.console import Console

    from tests.unit.pipelex.cli.dev.conftest import GitRepo

PYTHON = shlex.quote(sys.executable)
PASSING_VERIFY = f"{PYTHON} -c 'print(1)'"
FAILING_VERIFY = f"{PYTHON} -c 'import sys; print(\"boom output\"); sys.exit(3)'"


def _manifest(*, verify_commands: list[str] | None = None) -> str:
    commands = verify_commands or []
    rendered_commands = ", ".join(f"'''{command}'''" for command in commands)
    return f"""
version = 1

[contracts.demo-docs]
description = "Demo docs must track demo source."
triggers = ["src/**/*.py"]
review = ["docs/demo.md"]
verify_commands = [{rendered_commands}]
"""


def _seed_repo(git_repo: GitRepo, *, verify_commands: list[str] | None = None) -> None:
    git_repo.write("src/demo.py", content="x = 1\n")
    git_repo.write("docs/demo.md", content="# Demo\n")
    git_repo.write("drift.toml", content=_manifest(verify_commands=verify_commands))
    git_repo.add_all()
    git_repo.commit("seed")


class TestDriftAckCmd:
    def test_ack_round_trip_then_check_green(self, git_repo: GitRepo, drift_console: Console) -> None:
        """Stage → ack → check green, with a passing verify command in the loop."""
        _seed_repo(git_repo, verify_commands=[PASSING_VERIFY])
        drift_ack_cmd("demo-docs", rationale="Initial review, docs match.", repo_root=git_repo.root)
        acks = load_all_acks(git_repo.root)
        assert acks["demo-docs"].rationale == "Initial review, docs match."
        assert acks["demo-docs"].reviewed_by == "Test User"
        assert "src/demo.py" in acks["demo-docs"].trigger_files
        drift_check_cmd(repo_root=git_repo.root)
        assert "PASSED" in drift_console.export_text()

    def test_ack_then_staged_edit_invalidates(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo)
        drift_ack_cmd("demo-docs", rationale="Initial review.", repo_root=git_repo.root)
        git_repo.write("src/demo.py", content="x = 2\n")
        git_repo.add("src/demo.py")
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)

    def test_verify_failure_aborts_without_writing(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo, verify_commands=[FAILING_VERIFY])
        with pytest.raises(DriftAckError, match="exit 3"):
            drift_ack_cmd("demo-docs", rationale="Should not be written.", repo_root=git_repo.root)
        assert not ack_file_path(git_repo.root, contract_id="demo-docs").exists()
        assert "boom output" in drift_console.export_text()

    def test_verify_stops_at_first_failure(self, git_repo: GitRepo) -> None:
        marker = git_repo.root / "second_ran.txt"
        second_command = f'{PYTHON} -c \'open("second_ran.txt", "w").write("ran")\''
        _seed_repo(git_repo, verify_commands=[FAILING_VERIFY, second_command])
        with pytest.raises(DriftAckError):
            drift_ack_cmd("demo-docs", rationale="nope", repo_root=git_repo.root)
        assert not marker.exists()

    def test_empty_rationale_rejected(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo)
        with pytest.raises(DriftAckError, match="rationale"):
            drift_ack_cmd("demo-docs", rationale="   ", repo_root=git_repo.root)

    def test_missing_rationale_option_rejected_by_cli(self, git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_repo.root)
        _seed_repo(git_repo)
        runner = CliRunner()
        result = runner.invoke(drift_app, ["ack", "demo-docs"])
        assert result.exit_code != 0

    def test_reviewed_by_defaults_from_git_config(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo)
        drift_ack_cmd("demo-docs", rationale="Default reviewer.", repo_root=git_repo.root)
        assert load_all_acks(git_repo.root)["demo-docs"].reviewed_by == "Test User"

    def test_by_overrides_git_config(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo)
        drift_ack_cmd("demo-docs", rationale="Agent review.", reviewed_by_override="claude/session-42", repo_root=git_repo.root)
        assert load_all_acks(git_repo.root)["demo-docs"].reviewed_by == "claude/session-42"

    def test_unset_user_name_without_by_is_hard_error(self, git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
        _seed_repo(git_repo)
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
        git_repo.git("config", "--unset", "user.name")
        with pytest.raises(DriftAckError, match="--by"):
            drift_ack_cmd("demo-docs", rationale="No identity.", repo_root=git_repo.root)
        assert not ack_file_path(git_repo.root, contract_id="demo-docs").exists()

    def test_unknown_contract_is_hard_error(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo)
        with pytest.raises(DriftAckError, match="no-such-contract"):
            drift_ack_cmd("no-such-contract", rationale="nope", repo_root=git_repo.root)

    def test_ack_permitted_with_dirty_tree_elsewhere(self, git_repo: GitRepo, drift_console: Console) -> None:
        """A clean tree is not required — only the trigger files' staged state matters."""
        _seed_repo(git_repo)
        git_repo.write("docs/demo.md", content="# Demo edited, unstaged\n")
        drift_ack_cmd("demo-docs", rationale="Dirty elsewhere is fine.", repo_root=git_repo.root)
        drift_check_cmd(repo_root=git_repo.root)
        assert "PASSED" in drift_console.export_text()

    def test_unstaged_trigger_edit_warns_and_covers_staged_content(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        staged_oid = read_staged_files(git_repo.root)["src/demo.py"]
        git_repo.write("src/demo.py", content="x = 999  # unstaged\n")
        drift_ack_cmd("demo-docs", rationale="Covers staged content only.", repo_root=git_repo.root)
        output = drift_console.export_text()
        assert "unstaged modifications" in output
        assert load_all_acks(git_repo.root)["demo-docs"].trigger_files["src/demo.py"] == staged_oid

    def test_untracked_trigger_file_warns(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        git_repo.write("src/brand_new.py", content="new = True\n")
        drift_ack_cmd("demo-docs", rationale="Untracked file present.", repo_root=git_repo.root)
        output = drift_console.export_text()
        assert "untracked file matches triggers" in output
        assert "src/brand_new.py" not in load_all_acks(git_repo.root)["demo-docs"].trigger_files

    def test_ack_file_is_auto_staged(self, git_repo: GitRepo) -> None:
        """The ack lands in the same index `drift check` reads — no forgot-to-add false green."""
        _seed_repo(git_repo)
        drift_ack_cmd("demo-docs", rationale="Initial review.", repo_root=git_repo.root)
        staged_paths = git_repo.git("diff", "--cached", "--name-only").splitlines()
        assert ".drift/acks/demo-docs.toml" in staged_paths

    def test_verify_contract_with_unstaged_trigger_fails_before_verify(self, git_repo: GitRepo) -> None:
        """With verify commands, a dirty matching trigger is a hard error and the verify commands never run."""
        marker = git_repo.root / "verify_ran.txt"
        marker_command = f'{PYTHON} -c \'open("verify_ran.txt", "w").write("ran")\''
        _seed_repo(git_repo, verify_commands=[marker_command])
        git_repo.write("src/demo.py", content="x = 2  # unstaged\n")
        with pytest.raises(DriftAckError, match="verify commands"):
            drift_ack_cmd("demo-docs", rationale="Should not be written.", repo_root=git_repo.root)
        assert not ack_file_path(git_repo.root, contract_id="demo-docs").exists()
        assert not marker.exists()

    def test_verify_contract_with_untracked_trigger_fails(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo, verify_commands=[PASSING_VERIFY])
        git_repo.write("src/brand_new.py", content="new = True\n")
        with pytest.raises(DriftAckError, match="verify commands"):
            drift_ack_cmd("demo-docs", rationale="Should not be written.", repo_root=git_repo.root)
        assert not ack_file_path(git_repo.root, contract_id="demo-docs").exists()

    def test_verify_that_dirties_a_trigger_fails_after_verify(self, git_repo: GitRepo) -> None:
        """A verify command that rewrites a trigger is caught by the post-verify recheck — the ack never certifies stale index bytes."""
        rewrite_trigger = f'{PYTHON} -c \'open("src/demo.py", "w").write("x = 2")\''
        _seed_repo(git_repo, verify_commands=[rewrite_trigger])
        # The tree is clean before verify (pre-check passes); the verify command then dirties the trigger.
        with pytest.raises(DriftAckError, match="verify commands"):
            drift_ack_cmd("demo-docs", rationale="Should not be written.", repo_root=git_repo.root)
        assert not ack_file_path(git_repo.root, contract_id="demo-docs").exists()

    def test_stage_failure_removes_written_ack(self, git_repo: GitRepo, mocker: MockerFixture) -> None:
        """If staging the written ack fails, the ack file is removed so a later check reports a missing ack, not a false green."""
        _seed_repo(git_repo)
        mocker.patch(
            "pipelex.cli.dev_cli.commands.drift.drift_cmd.stage_file",
            side_effect=DriftGitError("git index locked"),
        )
        with pytest.raises(DriftAckError, match="staging"):
            drift_ack_cmd("demo-docs", rationale="Staging will fail.", repo_root=git_repo.root)
        assert not ack_file_path(git_repo.root, contract_id="demo-docs").exists()
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)
