"""Unit tests for the subprocess edges of `pipelex-dev store-test-durations`.

The pure refresh policies live in `duration_map.py` and are covered by the `test_duration_map_*`
modules; what is tested here is how the command reads pytest's exit codes and how it hands pytest the tests
to measure.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.dev_cli.commands.store_test_durations_cmd import (
    PYTEST_EXIT_NO_TESTS_COLLECTED,
    _collect_node_ids,  # pyright: ignore[reportPrivateUsage]
    _run_and_store,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

MODULE = "pipelex.cli.dev_cli.commands.store_test_durations_cmd"


class TestStoreTestDurationsCmd:
    def _patch_collection(self, mocker: MockerFixture, *, returncode: int, stdout: str = "") -> None:
        mocker.patch(
            f"{MODULE}.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=""),
        )

    def test_reads_the_collected_node_ids(self, mocker: MockerFixture) -> None:
        stdout = "tests/unit/test_a.py::TestA::test_one\ntests/unit/test_a.py::TestA::test_two\n\n2 tests collected in 0.10s\n"
        self._patch_collection(mocker, returncode=0, stdout=stdout)
        assert _collect_node_ids(markers="unit") == [
            "tests/unit/test_a.py::TestA::test_one",
            "tests/unit/test_a.py::TestA::test_two",
        ]

    def test_an_empty_selection_is_a_no_op_rather_than_a_collection_failure(self, mocker: MockerFixture) -> None:
        """An exit code of 5 means a marker expression matched nothing, which is legitimate, not a failure.

        The run step already treats 5 this way, and so does `make gha-tests` (`|| [ $? = 5 ]`); the
        collection step must agree, or a marker expression that excludes everything aborts the refresh.
        """
        self._patch_collection(mocker, returncode=PYTEST_EXIT_NO_TESTS_COLLECTED, stdout="no tests collected (306 deselected)\n")
        assert _collect_node_ids(markers="nothing_matches_this") == []

    def test_a_real_collection_failure_still_aborts(self, mocker: MockerFixture) -> None:
        """A broken conftest or an import error must not be mistaken for an empty selection."""
        self._patch_collection(mocker, returncode=1, stdout="ERROR collecting tests/unit/test_a.py\n")
        with pytest.raises(SystemExit) as exit_info:
            _collect_node_ids(markers="unit")
        assert exit_info.value.code == 1

    def test_the_tests_to_measure_go_through_an_args_file_rather_than_argv(self, mocker: MockerFixture) -> None:
        """Thousands of parametrized node ids overflow the OS argument limit, so pytest reads them from `@file`."""
        node_ids = [f"tests/unit/test_a.py::test_case[{index}]" for index in range(5000)]
        seen: dict[str, Any] = {}

        def fake_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            args_files = [arg for arg in argv if arg.startswith("@")]
            seen["argv"] = argv
            seen["file_lines"] = Path(args_files[0][1:]).read_text(encoding="utf-8").splitlines() if len(args_files) == 1 else None
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

        mocker.patch(f"{MODULE}.subprocess.run", side_effect=fake_run)
        assert _run_and_store(markers="unit", node_ids=node_ids) == 0
        assert seen["file_lines"] == node_ids
        assert not any("::" in arg for arg in seen["argv"])

    def test_a_full_run_passes_no_args_file(self, mocker: MockerFixture) -> None:
        run = mocker.patch(
            f"{MODULE}.subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        )
        assert _run_and_store(markers="unit", node_ids=None) == 0
        argv = run.call_args.args[0]
        assert not any(arg.startswith("@") for arg in argv)
