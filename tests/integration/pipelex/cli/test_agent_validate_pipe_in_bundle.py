from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_bundle_core,  # noqa: PLC2701
    validate_pipe_in_bundle_core,  # noqa: PLC2701
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipeline.validate_bundle import ValidateBundleError

if TYPE_CHECKING:
    from collections.abc import Iterator

# A fully-implemented leaf pipe plus an UNRELATED standalone signature that nothing reaches.
_BUNDLE_IMPLEMENTED_PLUS_UNRELATED_SIGNATURE = """
domain = "slice_bundle"

[concept]
SliceDoc = "A document for the --pipe slice test."
SliceNote = "A note for the --pipe slice test."

[pipe.implemented_pipe]
type = "PipeLLM"
description = "Fully implemented leaf pipe."
inputs = { doc = "SliceDoc" }
output = "Text"
prompt = "Extract text from $doc."

[pipe.draft_pipe]
type = "PipeSignature"
description = "Unrelated draft signature, reached by nothing."
inputs = { note = "SliceNote" }
output = "SliceNote"
"""

# A controller that reaches a signature through its dependency graph.
_BUNDLE_CALLER_OF_SIGNATURE = """
domain = "slice_caller"

[concept]
CallerDoc = "A document for the caller slice test."
CallerSummary = "A summary for the caller slice test."

[pipe.caller_seq]
type = "PipeSequence"
description = "Caller sequence reaching a signature step."
inputs = { doc = "CallerDoc" }
output = "CallerSummary"
steps = [ { pipe = "summary_sig", result = "summary" } ]

[pipe.summary_sig]
type = "PipeSignature"
description = "Signature placeholder for the summary step."
inputs = { doc = "CallerDoc" }
output = "CallerSummary"
"""


@pytest.fixture
def implemented_plus_signature_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_IMPLEMENTED_PLUS_UNRELATED_SIGNATURE)
        yield path


@pytest.fixture
def caller_of_signature_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_CALLER_OF_SIGNATURE)
        yield path


class TestAgentValidatePipeInBundle:
    def test_pipe_slice_strict_validates_implemented_pipe_despite_unrelated_signature(
        self,
        implemented_plus_signature_dir: Path,
    ) -> None:
        # --pipe selects one implemented slice: strict validation succeeds even though the bundle
        # also contains an unrelated standalone signature (which whole-bundle strict would reject).
        result = asyncio.run(
            validate_pipe_in_bundle_core(
                bundle_path=implemented_plus_signature_dir / "bundle.mthds",
                pipe_code="implemented_pipe",
                library_dirs=[implemented_plus_signature_dir],
            )
        )
        assert result["success"] is True
        pipe_codes = {entry["pipe_code"] for entry in result["validated_pipes"]}
        assert "implemented_pipe" in pipe_codes

    def test_whole_bundle_strict_still_rejects_unrelated_signature(
        self,
        implemented_plus_signature_dir: Path,
    ) -> None:
        # The whole-bundle path keeps strict semantics: a bundle that merely *contains* a signature
        # is rejected (by design), even when the signature is unreached.
        with pytest.raises(ValidateBundleError) as exc_info:
            asyncio.run(
                validate_bundle_core(
                    bundle_path=implemented_plus_signature_dir / "bundle.mthds",
                    library_dirs=[implemented_plus_signature_dir],
                )
            )
        assert exc_info.value.signature_check_error is not None

    def test_pipe_slice_strict_rejects_pipe_that_reaches_signature(
        self,
        caller_of_signature_dir: Path,
    ) -> None:
        # --pipe does NOT loosen strict mode for the *selected* pipe: if the requested pipe itself
        # reaches a signature, strict validation still fails.
        with pytest.raises(ValidateBundleError) as exc_info:
            asyncio.run(
                validate_pipe_in_bundle_core(
                    bundle_path=caller_of_signature_dir / "bundle.mthds",
                    pipe_code="caller_seq",
                    library_dirs=[caller_of_signature_dir],
                )
            )
        assert exc_info.value.signature_check_error is not None

    def test_pipe_slice_unknown_pipe_raises_not_found(
        self,
        implemented_plus_signature_dir: Path,
    ) -> None:
        # Selecting a pipe that is not defined in the bundle is an error, not a vacuous success.
        with pytest.raises(PipeNotFoundError):
            asyncio.run(
                validate_pipe_in_bundle_core(
                    bundle_path=implemented_plus_signature_dir / "bundle.mthds",
                    pipe_code="does_not_exist",
                    library_dirs=[implemented_plus_signature_dir],
                )
            )
