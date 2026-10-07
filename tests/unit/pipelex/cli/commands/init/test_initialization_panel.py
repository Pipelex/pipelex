"""The confirmation panel says what a run will do, a reset of the inference backends to the kit's defaults included."""

from __future__ import annotations

import pytest
from rich.console import Console

from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel


def _panel_text(*, asks_setup_path: bool, reset: bool, needs_inference: bool = True) -> str:
    console = Console(width=300, record=True, color_system=None)
    console.print(
        build_initialization_panel(
            needs_config=True,
            needs_inference=needs_inference,
            needs_routing=False,
            needs_telemetry=True,
            reset=reset,
            check_credentials=True,
            asks_setup_path=asks_setup_path,
        )
    )
    return console.export_text()


class TestInitializationPanel:
    @pytest.mark.parametrize("asks_setup_path", [True, False])
    def test_a_reset_that_touches_inference_says_the_backends_go_back_to_the_kit_defaults(self, asks_setup_path: bool) -> None:
        text = _panel_text(asks_setup_path=asks_setup_path, reset=True)

        assert "inference backends" in text
        assert "kit's defaults" in text

    def test_the_question_names_both_paths(self) -> None:
        text = _panel_text(asks_setup_path=True, reset=True)

        assert "on the hosted Pipelex API" in text
        assert "on this machine" in text
        assert "pipelex init inference" in text

    def test_a_run_that_does_not_touch_inference_says_nothing_about_the_backends(self) -> None:
        text = _panel_text(asks_setup_path=False, reset=True, needs_inference=False)

        assert "kit's defaults" not in text
