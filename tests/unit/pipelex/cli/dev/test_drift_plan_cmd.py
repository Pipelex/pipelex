"""Unit tests for `pipelex-dev drift plan`: packet content, diff reporting, exact ack invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.drift.core import compute_current_digest
from pipelex.cli.dev_cli.commands.drift.drift_cmd import drift_plan_cmd
from pipelex.cli.dev_cli.commands.drift.exceptions import DriftError
from pipelex.cli.dev_cli.commands.drift.git_adapter import read_staged_files
from pipelex.cli.dev_cli.commands.drift.models import DriftAck, load_manifest, save_ack

if TYPE_CHECKING:
    from pathlib import Path

    from tests.unit.pipelex.cli.dev.conftest import GitRepo

MANIFEST = """
version = 1

[contracts.demo-docs]
description = "Demo docs must track demo source."
triggers = ["src/**/*.py"]
review = ["docs/demo.md"]
verify_commands = ["make tb"]

[contracts.other-docs]
description = "Other docs must track other source."
triggers = ["other/**/*.py"]
review = ["docs/other.md"]
"""


def _seed_repo(git_repo: GitRepo) -> None:
    git_repo.write("src/demo.py", content="x = 1\n")
    git_repo.write("docs/demo.md", content="# Demo\n")
    git_repo.write("other/mod.py", content="y = 1\n")
    git_repo.write("docs/other.md", content="# Other\n")
    git_repo.write("drift.toml", content=MANIFEST)
    git_repo.add_all()
    git_repo.commit("seed")


def _ack_contract(repo_root: Path, *, contract_id: str, rationale: str = "test ack") -> None:
    manifest = load_manifest(repo_root)
    staged_oids = read_staged_files(repo_root)
    result = compute_current_digest(manifest.contracts[contract_id], contract_id=contract_id, staged_oids=staged_oids)
    ack = DriftAck(
        contract=contract_id,
        digest=result.digest,
        reviewed_by="tester",
        reviewed_at="2026-07-03T14:12:09Z",
        rationale=rationale,
        trigger_files=result.trigger_files,
    )
    save_ack(ack, repo_root=repo_root)


class TestDriftPlanCmd:
    def test_initial_review_lists_all_trigger_files_as_added(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        _seed_repo(git_repo)
        drift_plan_cmd(repo_root=git_repo.root)
        output = capfd.readouterr().out
        assert "## Open contract: demo-docs" in output
        assert "no previous ack — initial review required" in output
        assert "- added: src/demo.py" in output
        assert "- docs/demo.md" in output

    def test_ack_invocation_is_exact_and_copy_pasteable(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        """Agents run the emitted make command verbatim — its shape is part of the contract."""
        _seed_repo(git_repo)
        drift_plan_cmd(repo_root=git_repo.root)
        output = capfd.readouterr().out
        assert 'make drift-ack CONTRACT=demo-docs RATIONALE="…"' in output
        assert 'make drift-ack CONTRACT=other-docs RATIONALE="…"' in output

    def test_modified_trigger_and_previous_rationale_are_reported(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs", rationale="Reviewed the demo docs.")
        git_repo.write("src/demo.py", content="x = 2\n")
        git_repo.write("src/new_mod.py", content="z = 1\n")
        git_repo.add_all()
        drift_plan_cmd("demo-docs", repo_root=git_repo.root)
        output = capfd.readouterr().out
        assert "- modified: src/demo.py" in output
        assert "- added: src/new_mod.py" in output
        assert '(by tester, 2026-07-03, "Reviewed the demo docs.")' in output

    def test_fulfilled_contracts_are_excluded(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        drift_plan_cmd(repo_root=git_repo.root)
        output = capfd.readouterr().out
        assert "## Open contract: demo-docs" not in output
        assert "## Open contract: other-docs" in output

    def test_all_fulfilled_prints_nothing_to_review(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        _ack_contract(git_repo.root, contract_id="other-docs")
        drift_plan_cmd(repo_root=git_repo.root)
        assert "All drift contracts are fulfilled" in capfd.readouterr().out

    def test_single_fulfilled_contract_argument(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        _seed_repo(git_repo)
        _ack_contract(git_repo.root, contract_id="demo-docs")
        drift_plan_cmd("demo-docs", repo_root=git_repo.root)
        assert "Contract 'demo-docs' is fulfilled" in capfd.readouterr().out

    def test_unknown_contract_argument_is_hard_error(self, git_repo: GitRepo) -> None:
        _seed_repo(git_repo)
        with pytest.raises(DriftError, match="no-such-contract"):
            drift_plan_cmd("no-such-contract", repo_root=git_repo.root)

    def test_verify_commands_are_listed(self, git_repo: GitRepo, capfd: pytest.CaptureFixture[str]) -> None:
        _seed_repo(git_repo)
        drift_plan_cmd("demo-docs", repo_root=git_repo.root)
        output = capfd.readouterr().out
        assert "**Verify commands (run by ack):**" in output
        assert "- make tb" in output
