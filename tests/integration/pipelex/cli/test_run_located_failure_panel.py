from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.run._run_core import _execute_run  # pyright: ignore[reportPrivateUsage]
from tests.integration.pipelex.pipeline.test_data import LocatedRunFailureTestData

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestRunLocatedFailurePanel:
    async def test_unserved_model_renders_the_model_panel_at_the_failing_step(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`pipelex run` on the model example renders the model panel naming the failing step, with the local-deck tip there only."""
        console = Console(width=400, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=console)
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=console)
        bundle_path = tmp_path / "located_failure_model.mthds"
        bundle_path.write_text(LocatedRunFailureTestData.MODEL_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exit_info:
            await _execute_run(
                pipe_code="two_steps",
                bundle_path=str(bundle_path),
                inputs='{"topic": "cats"}',
                save_working_memory=False,
                working_memory_path=None,
                save_main_stuff=False,
                no_pretty_print=True,
                graph=False,
                graph_full_data=None,
                output_dir=str(tmp_path / "outputs"),
                dry_run=False,
                mock_usage=False,
                mock_inputs=False,
                library_dir=None,
            )

        assert exit_info.value.exit_code == 1
        panel = console.export_text()
        assert "Pipe run failed because a model wasn't available" in panel
        assert "Pipe:       'summarize' (PipeLLM)" in panel
        assert f"Model:      '{LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE}'" in panel
        assert "Pipe Stack: two_steps → summarize" in panel
        assert f"Error: Model handle '{LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE}' was not found in the model deck." in panel
        # The local-deck remedy lives in the panel's tip, and nowhere in the error's own message.
        assert "💡 Tip: Your local model deck may be out of date" in panel
        assert "run 'pipelex init inference'" in panel
        # The one-line fallback naming the entry pipe is not printed.
        assert "Failed to execute pipeline" not in capsys.readouterr().err
