from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import typer

from pipelex.cli.commands.validate._validate_core import _validate_pipe_or_bundle  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "signature_bundles"
_SIGNATURE_ONLY = _FIXTURE_DIR / "signature_only.mthds"


class TestSignatureValidationCli:
    def test_cli_validate_signature_bundle_strict_fails(self) -> None:
        # Strict mode (default): CLI exits with code 1 via typer.Exit when bundle reaches a signature.
        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(
                _validate_pipe_or_bundle(
                    bundle_path=_SIGNATURE_ONLY,
                    library_dirs=[_FIXTURE_DIR],
                )
            )
        assert exc_info.value.exit_code == 1

    def test_cli_validate_signature_bundle_lenient_passes(self) -> None:
        # Lenient mode: signatures are tolerated; CLI completes without raising.
        asyncio.run(
            _validate_pipe_or_bundle(
                bundle_path=_SIGNATURE_ONLY,
                library_dirs=[_FIXTURE_DIR],
                allow_signatures=True,
            )
        )
