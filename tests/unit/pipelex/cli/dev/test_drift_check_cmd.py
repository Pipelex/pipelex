"""Unit tests for `pipelex-dev drift check`: every failure class plus the all-green pass."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.drift.core import compute_current_digest
from pipelex.cli.dev_cli.commands.drift.drift_cmd import drift_check_cmd
from pipelex.cli.dev_cli.commands.drift.exceptions import DriftManifestError
from pipelex.cli.dev_cli.commands.drift.git_adapter import read_staged_files
from pipelex.cli.dev_cli.commands.drift.models import DriftAck, ack_file_path, load_manifest, save_ack

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from tests.unit.pipelex.cli.dev.conftest import GitRepo

MANIFEST = """
version = 1

[contracts.demo-docs]
description = "Demo docs must track demo source."
triggers = ["src/**/*.py"]
review = ["docs/demo.md"]
"""


def _seed_repo(git_repo: GitRepo, *, manifest: str = MANIFEST) -> None:
    git_repo.write("src/demo.py", content="x = 1\n")
    git_repo.write("docs/demo.md", content="# Demo\n")
    git_repo.write("drift.toml", content=manifest)
    git_repo.add_all()
    git_repo.commit("seed")


def _ack_contract(repo_root: Path, *, contract_id: str) -> None:
    """Record a valid ack for the current index state, bypassing the ack command."""
    manifest = load_manifest(repo_root)
    staged_oids = read_staged_files(repo_root)
    result = compute_current_digest(manifest.contracts[contract_id], contract_id=contract_id, staged_oids=staged_oids)
    ack = DriftAck(
        contract=contract_id,
        digest=result.digest,
        reviewed_by="tester",
        reviewed_at="2026-07-03T00:00:00Z",
        rationale="test ack",
        trigger_files=result.trigger_files,
    )
    save_ack(ack, repo_root=repo_root)


class TestDriftCheckCmd:
    def test_all_green_passes(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        drift_check_cmd(repo_root=git_repo.root)
        assert "PASSED" in drift_console.export_text()

    def test_missing_ack_fails_and_points_to_plan(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        with pytest.raises(SystemExit) as exc_info:
            drift_check_cmd(repo_root=git_repo.root)
        assert exc_info.value.code == 1
        output = drift_console.export_text()
        assert "no ack recorded" in output
        assert "run `make drift-plan`" in output

    def test_staged_edit_after_ack_fails(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        git_repo.write("src/demo.py", content="x = 2\n")
        git_repo.add("src/demo.py")
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)
        output = drift_console.export_text()
        assert "changed since last ack" in output
        assert "run `make drift-plan`" in output

    def test_unstaged_edit_after_ack_still_passes(self, git_repo: GitRepo, drift_console: Console) -> None:
        """Index semantics: an edit that is not staged does not open the contract."""
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        git_repo.write("src/demo.py", content="x = 2\n")
        drift_check_cmd(repo_root=git_repo.root)
        assert "PASSED" in drift_console.export_text()

    def test_dead_trigger_glob_fails_with_manifest_hint(self, git_repo: GitRepo, drift_console: Console) -> None:
        manifest = """
version = 1

[contracts.demo-docs]
description = "Demo docs must track demo source."
triggers = ["nonexistent/**"]
review = ["docs/demo.md"]
"""
        _seed_repo(git_repo, manifest=manifest)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)
        output = drift_console.export_text()
        assert "trigger pattern 'nonexistent/**' matches no tracked file" in output
        assert "edit drift.toml first" in output

    def test_zero_match_review_target_fails(self, git_repo: GitRepo, drift_console: Console) -> None:
        """Rot symmetry: a review target matching no tracked file is as hard an error as a dead trigger."""
        manifest = """
version = 1

[contracts.demo-docs]
description = "Demo docs must track demo source."
triggers = ["src/**/*.py"]
review = ["docs/missing.md"]
"""
        _seed_repo(git_repo, manifest=manifest)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)
        output = drift_console.export_text()
        assert "review target 'docs/missing.md' matches no tracked file" in output

    def test_orphan_ack_fails(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        orphan = DriftAck(
            contract="removed-contract",
            digest="sha256:dead",
            reviewed_by="tester",
            reviewed_at="2026-07-03T00:00:00Z",
            rationale="orphan",
            trigger_files={},
        )
        save_ack(orphan, repo_root=git_repo.root)
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)
        assert "no matching contract" in drift_console.export_text()

    def test_ack_contract_field_mismatch_fails(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        ack_path = ack_file_path(git_repo.root, contract_id="demo-docs")
        ack_path.write_text(ack_path.read_text().replace('contract = "demo-docs"', 'contract = "other-name"'))
        with pytest.raises(SystemExit):
            drift_check_cmd(repo_root=git_repo.root)
        assert "does not match its filename stem" in drift_console.export_text()

    def test_schema_invalid_manifest_is_hard_error(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo, manifest="version = 1\n\n[contracts.demo-docs]\ntriggers = []\n")
        with pytest.raises(DriftManifestError):
            drift_check_cmd(repo_root=git_repo.root)

    def test_quiet_success_is_single_line(self, git_repo: GitRepo, drift_console: Console) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        drift_check_cmd(quiet=True, repo_root=git_repo.root)
        assert "✓ Drift check: PASSED" in drift_console.export_text()
