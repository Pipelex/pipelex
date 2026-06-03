from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.validate._validate_core import (
    _validate_pipe_or_bundle,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    do_validate_all_libraries_and_dry_run,  # noqa: PLC2701
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_BUNDLE_WITH_SIGNATURE = """
domain = "sigsummary"

[concept]
SummaryDoc = "A document used in signature-summary tests."
SummaryOut = "A summary used in signature-summary tests."

[pipe.caller_seq]
type = "PipeSequence"
description = "Caller sequence referencing a signature step."
inputs = { doc = "SummaryDoc" }
output = "SummaryOut"
steps = [ { pipe = "summary_sig", result = "summary" } ]

[pipe.summary_sig]
type = "PipeSignature"
description = "Signature placeholder for the summary step."
inputs = { doc = "SummaryDoc" }
output = "SummaryOut"
"""

_BUNDLE_WITHOUT_SIGNATURE = """
domain = "sigsummary_clean"

[concept]
CleanDoc = "A document used in signature-summary tests."
"""


@pytest.fixture
def signature_summary_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_WITH_SIGNATURE)
        yield path


@pytest.fixture
def clean_bundle_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_WITHOUT_SIGNATURE)
        yield path


class TestValidateSignaturesSummary:
    def test_validate_all_lenient_appends_signature_count(
        self,
        signature_summary_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        do_validate_all_libraries_and_dry_run(
            library_dirs=[signature_summary_dir],
            allow_signatures=True,
        )
        captured = capsys.readouterr()
        assert "Setup sequence passed OK" in captured.out
        assert "(1 signature)" in captured.out

    def test_validate_all_strict_summary_unchanged(
        self,
        clean_bundle_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        do_validate_all_libraries_and_dry_run(
            library_dirs=[clean_bundle_dir],
            allow_signatures=False,
        )
        captured = capsys.readouterr()
        assert "Setup sequence passed OK" in captured.out
        assert "signature" not in captured.out.lower()

    def test_validate_bundle_lenient_appends_signature_count(
        self,
        signature_summary_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        asyncio.run(
            _validate_pipe_or_bundle(
                bundle_path=signature_summary_dir / "bundle.mthds",
                library_dirs=[signature_summary_dir],
                allow_signatures=True,
            )
        )
        captured = capsys.readouterr()
        assert "Successfully validated bundle" in captured.out
        assert "(1 signature)" in captured.out

    def test_validate_pipe_lenient_appends_signature_count(
        self,
        signature_summary_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        asyncio.run(
            _validate_pipe_or_bundle(
                pipe_code="caller_seq",
                library_dirs=[signature_summary_dir],
                allow_signatures=True,
            )
        )
        captured = capsys.readouterr()
        assert "Successfully validated pipe 'caller_seq'" in captured.out
        assert "(1 signature)" in captured.out
