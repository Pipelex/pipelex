"""The `pipelex codegen check` command: the 0/1/2 offline-verdict exit codes (no engine boot).

The check is offline by design — it never boots Pipelex — so these drive the command directly over a
real generated tree and assert the exit-code policy: 0 current, 1 drift present, 2 no lock (no verdict).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.codegen.check_cmd import codegen_check_cmd
from pipelex.codegen.emission import write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget, EmittedFile

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_FILES = [EmittedFile(filename="models.py", content="# h\nclass A:\n    pass\n")]


class TestCodegenCheckCli:
    def _generate(self, root: Path) -> None:
        write_stamped_projection(
            _FILES,
            output_dir=root,
            crate_fingerprint="fp1",
            engine_version="0.1.0",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )

    def test_no_lock_is_exit_2(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            codegen_check_cmd(root=str(tmp_path))
        assert exc_info.value.exit_code == 2

    def test_malformed_lock_is_exit_2(self, tmp_path: Path) -> None:
        (tmp_path / "codegen.lock").write_text("not = valid = toml [[", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            codegen_check_cmd(root=str(tmp_path))

        assert exc_info.value.exit_code == 2

    def test_expands_home_relative_root(self, mocker: MockerFixture) -> None:
        check = mocker.patch(
            "pipelex.cli.commands.codegen.check_cmd.run_codegen_check", return_value=mocker.MagicMock(lock_found=True, is_current=True)
        )

        codegen_check_cmd(root="~/generated")

        assert check.call_args.kwargs["root"] == Path.home() / "generated"

    def test_current_tree_is_exit_0(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        # A current tree does not raise (implicit exit 0).
        codegen_check_cmd(root=str(tmp_path))

    def test_drifted_tree_is_exit_1(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        target = tmp_path / "models.py"
        target.write_text(target.read_text(encoding="utf-8") + "drift = 1\n", encoding="utf-8")
        with pytest.raises(typer.Exit) as exc_info:
            codegen_check_cmd(root=str(tmp_path))
        assert exc_info.value.exit_code == 1
