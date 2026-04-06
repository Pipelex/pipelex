"""Regression test: standard CLI factory must handle InferenceSetupRequiredError.

The agent CLI factory catches InferenceSetupRequiredError and prints a friendly
markdown message. The standard CLI factory must also catch it so that first-run
users of ``pipelex run`` get a user-friendly message instead of an unhandled traceback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.system.pipelex_service.exceptions import InferenceSetupRequiredError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

CLI_FACTORY_MODULE = "pipelex.cli.cli_factory"


class TestCliFactory:
    """Verify that make_pipelex_for_cli() handles setup errors gracefully."""

    def test_first_run_catches_inference_setup_required(
        self,
        mocker: MockerFixture,
    ) -> None:
        """On first run, InferenceSetupRequiredError must be caught and exit cleanly."""
        mocker.patch(
            f"{CLI_FACTORY_MODULE}.Pipelex.make",
            side_effect=InferenceSetupRequiredError(),
        )

        with pytest.raises(typer.Exit):
            make_pipelex_for_cli(
                context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN,
                needs_inference=True,
            )
