from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_log_calls_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.check_log_calls_cmd import check_log_calls_cmd
from pipelex.cli.dev_cli.commands.log_call_guard import (
    BASELINE_FILE,
    GUARD_MODULE_FILE,
    LogCallGuardError,
    build_baseline,
    collect_offending_calls,
    load_trusted_baseline,
    render_baseline,
    resolve_merge_base,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from tests.unit.pipelex.cli.dev.conftest import GitRepo

#: Wide enough that no assertion below depends on where Rich decides to wrap.
CONSOLE_WIDTH = 400

SAMPLE_MODULE = "pipelex/core/sample_module.py"
API_MODULE = "api/pipelex_api/routes.py"

CONVERTED = 'from pipelex import log\n\ndef load(alias):\n    log.warning("Loaded a dependency", fields={"dependency_alias": alias})\n'
INTERPOLATED = 'from pipelex import log\n\ndef load(alias):\n    log.warning(f"Loaded {alias}")\n'
LISTED_SIGNATURE = 'warning: f"Loaded {alias}" [f-string]'


class TestLogCallTrustedBaseline:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH))
        return buffer

    @staticmethod
    def _write_tree(*, repo: GitRepo, sample_source: str, with_guard: bool = True, with_baseline: bool = True) -> None:
        """A tree the guard can scan: both scan roots, the guard's own module, and the baseline that matches the sample."""
        repo.write(SAMPLE_MODULE, content=sample_source)
        repo.write(API_MODULE, content=CONVERTED)
        if with_guard:
            repo.write(GUARD_MODULE_FILE.as_posix(), content="# the guard\n")
        if with_baseline:
            offending = collect_offending_calls(repo_root=repo.root)
            repo.write(BASELINE_FILE.as_posix(), content=render_baseline(baseline=build_baseline(offending=offending)))

    def test_the_trusted_baseline_is_read_at_the_revision(self, git_repo: GitRepo) -> None:
        self._write_tree(repo=git_repo, sample_source=INTERPOLATED)
        git_repo.add_all()
        git_repo.commit("guard with a baseline")
        assert load_trusted_baseline(repo_root=git_repo.root, ref="HEAD") == {f"{SAMPLE_MODULE}::load": [LISTED_SIGNATURE]}

    @pytest.mark.parametrize(
        ("topic", "with_guard", "expected"),
        [
            ("a revision that runs the guard has an empty baseline", True, {}),
            ("a revision before the guard has none to compare with", False, None),
        ],
    )
    def test_a_revision_without_the_baseline_file(
        self, git_repo: GitRepo, topic: str, with_guard: bool, expected: dict[str, list[str]] | None
    ) -> None:
        self._write_tree(repo=git_repo, sample_source=CONVERTED, with_guard=with_guard, with_baseline=False)
        git_repo.add_all()
        git_repo.commit("no baseline")
        assert load_trusted_baseline(repo_root=git_repo.root, ref="HEAD") == expected, topic

    def test_a_revision_that_does_not_resolve_is_an_error(self, git_repo: GitRepo) -> None:
        self._write_tree(repo=git_repo, sample_source=CONVERTED)
        git_repo.add_all()
        git_repo.commit("guard")
        with pytest.raises(LogCallGuardError, match="does not resolve to a commit"):
            load_trusted_baseline(repo_root=git_repo.root, ref="no-such-branch")

    def test_the_merge_base_resolves_or_is_none(self, git_repo: GitRepo) -> None:
        self._write_tree(repo=git_repo, sample_source=CONVERTED)
        git_repo.add_all()
        git_repo.commit("base")
        base_commit = git_repo.git("rev-parse", "HEAD").strip()
        git_repo.git("branch", "base")
        git_repo.write("pipelex/core/other_module.py", content=CONVERTED)
        git_repo.add_all()
        git_repo.commit("topic")
        assert resolve_merge_base(repo_root=git_repo.root, ref="base") == base_commit
        assert resolve_merge_base(repo_root=git_repo.root, ref="no-such-branch") is None

    def test_adding_a_violation_with_its_exemption_fails_against_the_base(
        self, git_repo: GitRepo, console_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tree and its baseline agree, so the tree check alone passes; the comparison with the base refuses the new entry."""
        self._write_tree(repo=git_repo, sample_source=CONVERTED)
        git_repo.add_all()
        git_repo.commit("base, clean")
        self._write_tree(repo=git_repo, sample_source=INTERPOLATED)
        monkeypatch.chdir(git_repo.root)

        check_log_calls_cmd(quiet=True)
        assert "✓ Log-call check: PASSED (1 baselined call(s) left)" in console_buffer.getvalue()

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(quiet=True, against="HEAD")

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "1 baseline signature(s) were added since 'HEAD'" in output
        assert f"{SAMPLE_MODULE}::load  listed 1 time(s), 0 at the base" in output
        assert LISTED_SIGNATURE in output

    def test_removing_an_entry_passes_against_the_base(self, git_repo: GitRepo, console_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
        self._write_tree(repo=git_repo, sample_source=INTERPOLATED)
        git_repo.add_all()
        git_repo.commit("base, one baselined call")
        self._write_tree(repo=git_repo, sample_source=CONVERTED)
        monkeypatch.chdir(git_repo.root)

        check_log_calls_cmd(quiet=True, against="HEAD")

        assert "✓ Log-call check: PASSED (0 baselined call(s) left, none added since 'HEAD')" in console_buffer.getvalue()

    def test_the_merge_base_comparison_runs_when_it_resolves(
        self, git_repo: GitRepo, console_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_tree(repo=git_repo, sample_source=CONVERTED)
        git_repo.add_all()
        git_repo.commit("base, clean")
        git_repo.git("branch", "base")
        self._write_tree(repo=git_repo, sample_source=INTERPOLATED)
        git_repo.add_all()
        git_repo.commit("topic, with an exemption it gave itself")
        monkeypatch.chdir(git_repo.root)

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(quiet=True, against_merge_base="base")

        assert exit_info.value.code == 1
        assert "were added since the merge base with base" in console_buffer.getvalue()

    @pytest.mark.parametrize(
        ("topic", "against_merge_base", "with_guard", "expected_notice"),
        [
            ("no merge base resolves", "no-such-branch", True, "no merge base of HEAD and 'no-such-branch' resolves"),
            ("the guard does not exist at the base", "base", False, "the log-call guard does not exist at the merge base with base"),
        ],
    )
    def test_a_comparison_that_cannot_run_says_so_and_checks_the_tree(
        self,
        git_repo: GitRepo,
        console_buffer: io.StringIO,
        monkeypatch: pytest.MonkeyPatch,
        topic: str,
        against_merge_base: str,
        with_guard: bool,
        expected_notice: str,
    ) -> None:
        self._write_tree(repo=git_repo, sample_source=CONVERTED, with_guard=with_guard, with_baseline=with_guard)
        git_repo.add_all()
        git_repo.commit("base")
        git_repo.git("branch", "base")
        self._write_tree(repo=git_repo, sample_source=INTERPOLATED)
        monkeypatch.chdir(git_repo.root)

        check_log_calls_cmd(quiet=True, against_merge_base=against_merge_base)

        output = console_buffer.getvalue()
        assert expected_notice in output, topic
        assert "✓ Log-call check: PASSED (1 baselined call(s) left)" in output, topic

    def test_an_unresolvable_trusted_revision_fails_the_check(
        self, git_repo: GitRepo, console_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_tree(repo=git_repo, sample_source=CONVERTED)
        git_repo.add_all()
        git_repo.commit("base")
        monkeypatch.chdir(git_repo.root)

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(quiet=True, against="no-such-branch")

        assert exit_info.value.code == 1
        assert "The revision 'no-such-branch' the log-call baseline is compared with does not resolve to a commit" in console_buffer.getvalue()

    def test_the_guard_module_path_names_this_guard(self) -> None:
        """A revision is read as running the guard when it holds this file, so a move of the module must move the constant."""
        repo_root = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent
        assert (repo_root / GUARD_MODULE_FILE).resolve() == Path(cmd_mod.__file__).resolve().parent / "log_call_guard.py"
