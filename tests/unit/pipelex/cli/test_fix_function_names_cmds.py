import json
from pathlib import Path

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.fix.function_names_cmd import fix_function_names_cmd as agent_fix_function_names_cmd
from pipelex.cli.commands.fix.function_names_cmd import fix_function_names_cmd

_MODULE = """\
from pipelex.system.registries.func_registry import pipe_func


@pipe_func(name="invoice_totals")
def compute_totals(working_memory):
    return working_memory
"""

_BUNDLE = """\
domain = "invoicing"

[pipe.totals]
type          = "PipeFunc"
description   = "Compute the totals"
output        = "Text"
function_name = "{flat_name}"
"""


def _method_folder(*, root: Path, flat_name: str) -> Path:
    method_dir = root / "invoicing"
    (method_dir / "funcs").mkdir(parents=True)
    (method_dir / "invoicing.mthds").write_text(_BUNDLE.format(flat_name=flat_name), encoding="utf-8")
    (method_dir / "funcs" / "totals.py").write_text(_MODULE, encoding="utf-8")
    return method_dir


class TestFixFunctionNamesCmds:
    def test_the_command_rewrites_the_method_and_reports_it(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        method_dir = _method_folder(root=tmp_path, flat_name="invoice_totals")

        fix_function_names_cmd(path=str(method_dir))

        out = capsys.readouterr().out
        assert "`invoice_totals` → `funcs.totals.compute_totals`" in out
        assert 'function_name = "funcs.totals.compute_totals"' in (method_dir / "invoicing.mthds").read_text(encoding="utf-8")
        assert "@pipe_func()\n" in (method_dir / "funcs" / "totals.py").read_text(encoding="utf-8")

    def test_the_command_writes_nothing_on_a_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        method_dir = _method_folder(root=tmp_path, flat_name="invoice_totals")

        fix_function_names_cmd(path=str(method_dir), dry_run=True)

        assert "Nothing was written" in capsys.readouterr().out
        assert (method_dir / "invoicing.mthds").read_text(encoding="utf-8") == _BUNDLE.format(flat_name="invoice_totals")

    @pytest.mark.parametrize(
        ("flat_name", "expected_exit_code"),
        [pytest.param("no_such_totals", 1, id="unresolved"), pytest.param("invoice_totals", None, id="complete")],
    )
    def test_the_command_exits_one_when_a_name_is_left(self, tmp_path: Path, flat_name: str, expected_exit_code: int | None) -> None:
        method_dir = _method_folder(root=tmp_path, flat_name=flat_name)

        if expected_exit_code is None:
            fix_function_names_cmd(path=str(method_dir))
            return
        with pytest.raises(typer.Exit) as exc_info:
            fix_function_names_cmd(path=str(method_dir))
        assert exc_info.value.exit_code == expected_exit_code

    def test_the_command_exits_two_on_a_path_that_is_no_folder(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            fix_function_names_cmd(path=str(tmp_path / "missing"))

        assert exc_info.value.exit_code == 2
        assert "is not a directory" in capsys.readouterr().err

    def test_the_agent_command_reports_its_verdict_in_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        method_dir = _method_folder(root=tmp_path, flat_name="no_such_totals")

        with pytest.raises(typer.Exit) as exc_info:
            agent_fix_function_names_cmd(path=str(method_dir), dry_run=True, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["is_complete"] is False
        assert payload["is_dry_run"] is True
        assert payload["changed_files"] == ["funcs/totals.py"]
        assert payload["rewrites"] == []
        assert payload["marker_removals"] == [{"module": "funcs/totals.py", "function": "compute_totals", "registered_name": "invoice_totals"}]
        (unresolved,) = payload["unresolved"]
        assert unresolved["pipe_code"] == "totals"
        assert unresolved["flat_name"] == "no_such_totals"
        assert payload["unresolved_markers"] == []

    def test_a_marker_whose_name_is_not_a_literal_exits_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        method_dir = _method_folder(root=tmp_path, flat_name="funcs.totals.compute_totals")
        module_file = method_dir / "funcs" / "totals.py"
        module_file.write_text(_MODULE.replace('(name="invoice_totals")', "(name=TOTALS_NAME)"), encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            agent_fix_function_names_cmd(path=str(method_dir), output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["is_complete"] is False
        assert payload["changed_files"] == []
        (marker,) = payload["unresolved_markers"]
        assert marker["module"] == "funcs/totals.py"
        assert marker["function"] == "compute_totals"
        assert marker["registered_name"] is None
        assert "(name=TOTALS_NAME)" in module_file.read_text(encoding="utf-8")

    def test_the_agent_command_reports_in_markdown_by_default(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        method_dir = _method_folder(root=tmp_path, flat_name="invoice_totals")

        agent_fix_function_names_cmd(path=str(method_dir))

        out = capsys.readouterr().out
        assert out.startswith("# Function names of the method at")
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
