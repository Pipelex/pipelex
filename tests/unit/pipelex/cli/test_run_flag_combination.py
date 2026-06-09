"""Unit tests for ``validate_run_flag_combination`` — the single owner of which run-flag combinations are legal.

The ``pipe`` / ``method`` / ``bundle`` run subcommands all delegate their ``--dry-run`` / ``--mock-inference`` /
``--mock-inputs`` guarding to this one function, so the three can't drift (review F3). The CLI-level wiring —
that each subcommand actually calls it — is pinned separately in ``test_mock_inference_cli_guard.py``; here we
pin the full truth table of the validator itself.
"""

import pytest
import typer

from pipelex.cli.commands.run._run_core import validate_run_flag_combination  # noqa: PLC2701


class TestRunFlagCombination:
    def test_mock_inputs_without_dry_run_is_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            validate_run_flag_combination(dry_run=False, mock_inference=False, mock_inputs=True)

    def test_mock_inference_with_dry_run_is_rejected(self) -> None:
        with pytest.raises(typer.Exit):
            validate_run_flag_combination(dry_run=True, mock_inference=True, mock_inputs=False)

    @pytest.mark.parametrize(
        ("dry_run", "mock_inference", "mock_inputs"),
        [
            (False, False, False),  # plain live run
            (True, False, False),  # plain dry run
            (False, True, False),  # mock-inference (live)
            (True, False, True),  # dry run with mock inputs
        ],
    )
    def test_legal_combinations_pass(self, dry_run: bool, mock_inference: bool, mock_inputs: bool) -> None:
        # No raise == legal (the function returns None and exits only on an illegal combination).
        validate_run_flag_combination(dry_run=dry_run, mock_inference=mock_inference, mock_inputs=mock_inputs)
