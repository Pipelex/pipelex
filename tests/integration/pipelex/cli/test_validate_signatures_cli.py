from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.validate._validate_core import (
    _validate_pipe_or_bundle,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    do_validate_all_libraries_and_dry_run,  # noqa: PLC2701
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_BUNDLE_WITH_SIGNATURE_CALLER = """
domain = "sigcli_caller"

[concept]
CliDoc = "A document used in CLI signature tests."
CliSummary = "A summary used in CLI signature tests."

[pipe.caller_seq]
type = "PipeSequence"
description = "Caller sequence referencing a signature step."
inputs = { doc = "CliDoc" }
output = "CliSummary"
steps = [ { pipe = "summary_sig", result = "summary" } ]

[pipe.summary_sig]
type = "PipeSignature"
description = "Signature placeholder for the summary step."
inputs = { doc = "CliDoc" }
output = "CliSummary"
"""

_BUNDLE_WITH_ORPHAN_SIGNATURE = """
domain = "sigcli_orphan"

[concept]
CliDoc = "A document used in CLI signature tests."
CliSummary = "A summary used in CLI signature tests."

[pipe.orphan_sig]
type = "PipeSignature"
description = "Orphan signature with no caller."
inputs = { doc = "CliDoc" }
output = "CliSummary"
"""


@pytest.fixture
def signature_caller_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_WITH_SIGNATURE_CALLER)
        yield path


@pytest.fixture
def orphan_signature_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_WITH_ORPHAN_SIGNATURE)
        yield path


class TestValidateSignaturesCli:
    def test_validate_bundle_strict_default_fails(
        self,
        signature_caller_dir: Path,
    ) -> None:
        # Strict mode (default): CLI exits with code 1 via typer.Exit when bundle reaches a signature.
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(
                _validate_pipe_or_bundle(
                    bundle_path=signature_caller_dir / "bundle.mthds",
                    library_dirs=[signature_caller_dir],
                )
            )
        assert exc_info.value.exit_code == 1

    def test_validate_bundle_allow_signatures_passes(self, signature_caller_dir: Path) -> None:
        # Lenient mode: signatures are tolerated; CLI completes without raising.
        asyncio.run(
            _validate_pipe_or_bundle(
                bundle_path=signature_caller_dir / "bundle.mthds",
                library_dirs=[signature_caller_dir],
                allow_signatures=True,
            )
        )

    def test_validate_all_strict_default_passes_with_orphan_signature(self, orphan_signature_dir: Path) -> None:
        # Orphan signature (no caller): strict --all should still succeed since signatures are filtered out.
        do_validate_all_libraries_and_dry_run(library_dirs=[orphan_signature_dir])

    def test_validate_all_strict_fails_with_caller_of_signature(self, signature_caller_dir: Path) -> None:
        # Non-signature pipe reaching a signature: strict --all must wrap SignaturesNotAllowedError
        # as a friendly typer.Exit(1) (consistent with the bundle/pipe paths), not bubble a raw
        # traceback to the user.
        with pytest.raises(typer.Exit) as exc_info:
            do_validate_all_libraries_and_dry_run(library_dirs=[signature_caller_dir])
        assert exc_info.value.exit_code == 1

    def test_validate_all_allow_signatures_passes(self, signature_caller_dir: Path) -> None:
        # Lenient mode: --all succeeds even when a non-signature pipe reaches a signature.
        do_validate_all_libraries_and_dry_run(library_dirs=[signature_caller_dir], allow_signatures=True)

    def test_validate_pipe_strict_default_fails_with_friendly_exit(
        self,
        signature_caller_dir: Path,
    ) -> None:
        # Regression (issue 6 / greptile): single-pipe validation must wrap SignaturesNotAllowedError
        # as typer.Exit(1) with a Rich error message, not bubble a raw traceback to the user.
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(
                _validate_pipe_or_bundle(
                    pipe_code="sigcli_caller.caller_seq",
                    library_dirs=[signature_caller_dir],
                )
            )
        assert exc_info.value.exit_code == 1

    def test_validate_pipe_allow_signatures_passes(
        self,
        signature_caller_dir: Path,
    ) -> None:
        # Sanity-check: lenient mode still completes without raising for the single-pipe path.
        asyncio.run(
            _validate_pipe_or_bundle(
                pipe_code="sigcli_caller.caller_seq",
                library_dirs=[signature_caller_dir],
                allow_signatures=True,
            )
        )
