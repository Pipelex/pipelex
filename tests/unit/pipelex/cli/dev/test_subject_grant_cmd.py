"""Unit tests for the `pipelex-dev subject-grant` command: refusals, sorted writes, and the transitional seed."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands.subject_grant_cmd import SEED_RATIONALE, subject_grant_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

_MODULE_SOURCE = """\
def render(node):
    return node


def build(spec, *, strict=False):
    return spec


def do_doctor_cmd(fix: bool):
    return fix


def all_keyword(*, alpha, beta):
    return alpha


def __dunder_like__(self, key, value):
    return key
"""

_OVERLOADS_SOURCE = """\
def parse(spec):
    return spec


def parse(data):
    return data
"""


def _read_registry(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / "subject_grants.toml").read_text(encoding="utf-8"))


class TestSubjectGrantCmd:
    console: Console

    @pytest.fixture(autouse=True)
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> Path:
        """A minimal repo tree (source module + empty registry) with cwd and console captured."""
        sample = tmp_path / "pipelex" / "sample"
        sample.mkdir(parents=True)
        (sample / "module.py").write_text(_MODULE_SOURCE, encoding="utf-8")
        (sample / "overloads.py").write_text(_OVERLOADS_SOURCE, encoding="utf-8")
        (tmp_path / "subject_grants.toml").write_text("version = 1\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        self.console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.dev_cli.commands.subject_grant_cmd.get_console", return_value=self.console)
        return tmp_path

    def test_grant_records_param_and_rewrites_sorted(self, repo: Path) -> None:
        """A grant validates the def, records the subject's param automatically, and keeps the file sorted."""
        subject_grant_cmd(func_key="pipelex/sample/module.py::render", rationale="Verb-object; single operand.", quiet=True)
        subject_grant_cmd(func_key="pipelex/sample/module.py::build", rationale="Verb-object; builds the spec.", quiet=True)
        data = _read_registry(repo)
        assert data["version"] == 1
        entry_keys = [key for key in data if key != "version"]
        assert entry_keys == sorted(entry_keys)
        assert data["pipelex/sample/module.py::render"] == {"param": "node", "rationale": "Verb-object; single operand."}
        assert data["pipelex/sample/module.py::build"] == {"param": "spec", "rationale": "Verb-object; builds the spec."}

    def test_grant_replaces_seeded_entry(self, repo: Path) -> None:
        """Re-granting a seeded entry is the review act: the placeholder and the seeded flag are dropped."""
        (repo / "subject_grants.toml").write_text(
            f'version = 1\n\n["pipelex/sample/module.py::render"]\nparam = "node"\nrationale = "{SEED_RATIONALE}"\nseeded = true\n',
            encoding="utf-8",
        )
        subject_grant_cmd(func_key="pipelex/sample/module.py::render", rationale="Reviewed for real.", quiet=True)
        data = _read_registry(repo)
        assert data["pipelex/sample/module.py::render"] == {"param": "node", "rationale": "Reviewed for real."}
        assert "reviewed (seeded entry replaced)" in self.console.export_text()

    def test_refuses_empty_rationale(self, repo: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/module.py::render", rationale="   ")
        assert exc_info.value.code == 1
        assert "rationale" in self.console.export_text()
        assert "render" not in _read_registry(repo)

    def test_refuses_literal_subject(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/module.py::do_doctor_cmd", rationale="please")
        assert exc_info.value.code == 1
        assert "literal-typed" in self.console.export_text()

    def test_refuses_non_positional_subject(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/module.py::all_keyword", rationale="please")
        assert exc_info.value.code == 1
        assert "no positional subject" in self.console.export_text()

    def test_refuses_missing_def(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/module.py::ghost", rationale="please")
        assert exc_info.value.code == 1
        assert "no def" in self.console.export_text()

    def test_refuses_exempt_def(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/module.py::__dunder_like__", rationale="please")
        assert exc_info.value.code == 1
        assert "exempt" in self.console.export_text()

    def test_refuses_malformed_key(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/module.py", rationale="please")
        assert exc_info.value.code == 1
        assert "FUNC key" in self.console.export_text()

    def test_refuses_disagreeing_overloads(self) -> None:
        """Same-qualname defs must agree on the subject name before one grant can cover them (D11)."""
        with pytest.raises(SystemExit) as exc_info:
            subject_grant_cmd(func_key="pipelex/sample/overloads.py::parse", rationale="please")
        assert exc_info.value.code == 1
        assert "disagree" in self.console.export_text()

    def test_seed_enters_every_ungranted_subject(self, repo: Path) -> None:
        """The transitional seed: grantable subjects enter as seeded=true; literal subjects are never seeded."""
        subject_grant_cmd(func_key=None, rationale=None, seed=True, quiet=True)
        data = _read_registry(repo)
        assert data["pipelex/sample/module.py::render"] == {"param": "node", "rationale": SEED_RATIONALE, "seeded": True}
        assert data["pipelex/sample/module.py::build"] == {"param": "spec", "rationale": SEED_RATIONALE, "seeded": True}
        assert data["pipelex/sample/overloads.py::parse"]["seeded"] is True
        assert "pipelex/sample/module.py::do_doctor_cmd" not in data  # literal — can never be granted
        assert "pipelex/sample/module.py::all_keyword" not in data  # no positional subject
        assert "pipelex/sample/module.py::__dunder_like__" not in data  # exempt

    def test_seed_reports_disagreeing_overloads_and_first_seen_wins(self, repo: Path) -> None:
        """Same-qualname defs disagreeing on the subject name: first one seen is seeded, the conflict is surfaced."""
        subject_grant_cmd(func_key=None, rationale=None, seed=True, quiet=True)
        data = _read_registry(repo)
        assert data["pipelex/sample/overloads.py::parse"]["param"] == "spec"  # source order: parse(spec) precedes parse(data)
        output = self.console.export_text()
        assert "disagree" in output
        assert "pipelex/sample/overloads.py::parse" in output

    def test_seed_is_idempotent_and_keeps_reviewed_entries(self, repo: Path) -> None:
        """A second seed adds nothing, and a reviewed (non-seeded) entry is never overwritten by seeding."""
        subject_grant_cmd(func_key="pipelex/sample/module.py::render", rationale="Reviewed for real.", quiet=True)
        subject_grant_cmd(func_key=None, rationale=None, seed=True, quiet=True)
        first = _read_registry(repo)
        subject_grant_cmd(func_key=None, rationale=None, seed=True, quiet=True)
        second = _read_registry(repo)
        assert first == second
        assert second["pipelex/sample/module.py::render"] == {"param": "node", "rationale": "Reviewed for real."}
