from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.base_exceptions import ErrorDomain
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_bundle_core,
    validate_pipe_in_bundle_core,
)
from pipelex.libraries.pipe.exceptions import EntryPipeNotFoundError

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
description = "Unrelated draft signature, reached by nothing."
inputs = { note = "SliceNote" }
output = "SliceNote"
"""

# A controller whose branch references an UNLOADED cross-package sub-pipe ("ext->otherpkg.missing_pipe").
# PipeParallel resolves its branches with an unguarded get_required_pipe, so validate_with_libraries
# raises PipeNotFoundError and the sliced sweep records the controller SKIPPED — never SUCCESS.
_BUNDLE_CROSS_PACKAGE_CONTROLLER = """
domain = "slice_xpkg"
description = "Bundle whose requested controller references an unloaded cross-package sub-pipe."

[concept.XpkgDoc]
description = "A document for the cross-package slice test."

[pipe.implemented_leaf]
type = "PipeLLM"
description = "A fully implemented sibling leaf."
inputs = { doc = "XpkgDoc" }
output = "Text"
prompt = "Summarize $doc"

[pipe.cross_parallel]
type = "PipeParallel"
description = "Parallel referencing an unloaded cross-package branch."
inputs = { doc = "XpkgDoc" }
output = "Composite"
add_each_output = true
branches = [
  { pipe = "ext->otherpkg.missing_pipe", result = "branch_result" },
]
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


@pytest.fixture
def cross_package_controller_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        (path / "bundle.mthds").write_text(_BUNDLE_CROSS_PACKAGE_CONTROLLER)
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
        pipe_refs = {entry["pipe_ref"] for entry in result["validated_pipes"]}
        # Identity is the namespaced pipe_ref (domain.code) on every validate surface.
        assert "slice_bundle.implemented_pipe" in pipe_refs
        # pending_signatures is library-wide: the unrelated standalone signature still counts, so even
        # this successful slice reports the bundle as not-yet-runnable.
        assert "slice_bundle.draft_pipe" in result["pending_signatures"]
        assert result["is_runnable"] is False

    def test_whole_bundle_strict_reports_unrelated_signature_as_pending(
        self,
        implemented_plus_signature_dir: Path,
    ) -> None:
        # Signatures are never an error (D-B): whole-bundle strict no longer rejects a bundle that merely
        # contains a standalone signature. It returns a valid-but-not-runnable envelope listing the
        # signature in pending_signatures; the bundle command's exit-code gate enforces the verdict.
        result = asyncio.run(
            validate_bundle_core(
                bundle_path=implemented_plus_signature_dir / "bundle.mthds",
                library_dirs=[implemented_plus_signature_dir],
            )
        )
        assert result["is_valid"] is True
        assert "slice_bundle.draft_pipe" in result["pending_signatures"]
        assert result["is_runnable"] is False
        # The implemented pipe is swept; the standalone signature pipe is excluded from the strict sweep.
        pipe_refs = {entry["pipe_ref"] for entry in result["validated_pipes"]}
        assert "slice_bundle.implemented_pipe" in pipe_refs
        assert "slice_bundle.draft_pipe" not in pipe_refs

    def test_pipe_slice_strict_reports_reached_signature_as_pending(
        self,
        caller_of_signature_dir: Path,
    ) -> None:
        # The requested pipe reaches a signature through its dependency graph. Signatures are never an
        # error (D-B): the slice is swept and dry-runs trivially (the signature sub-pipe mints a mock);
        # the reached signature is reported library-wide via pending_signatures, leaving it not-runnable.
        result = asyncio.run(
            validate_pipe_in_bundle_core(
                bundle_path=caller_of_signature_dir / "bundle.mthds",
                pipe_code="caller_seq",
                library_dirs=[caller_of_signature_dir],
            )
        )
        assert result["is_valid"] is True
        assert "slice_caller.summary_sig" in result["pending_signatures"]
        assert result["is_runnable"] is False
        pipe_refs = {entry["pipe_ref"] for entry in result["validated_pipes"]}
        assert "slice_caller.caller_seq" in pipe_refs

    def test_pipe_slice_unknown_pipe_raises_not_found(
        self,
        implemented_plus_signature_dir: Path,
    ) -> None:
        # Selecting a pipe that is not defined in the bundle is an error, not a vacuous success. The
        # `--pipe` / `pipe_ref` selector is entry-shaped input the caller typed, so the miss must be
        # the INPUT-domained EntryPipeNotFoundError — not the undomained base, which every
        # presentation would render as a 500 server fault for a mistake only the caller can fix.
        with pytest.raises(EntryPipeNotFoundError) as exc_info:
            asyncio.run(
                validate_pipe_in_bundle_core(
                    bundle_path=implemented_plus_signature_dir / "bundle.mthds",
                    pipe_code="does_not_exist",
                    library_dirs=[implemented_plus_signature_dir],
                )
            )
        report = exc_info.value.to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.http_status == 422
        # The raise site keeps its own bundle-scoped wording, which names the caller's own code.
        assert "does_not_exist" in report.message

    def test_pipe_slice_cross_package_controller_reports_skipped_not_success(
        self,
        cross_package_controller_dir: Path,
    ) -> None:
        # Regression for the hardcoded-"SUCCESS" bug (#1): when the requested pipe is a controller that
        # references an UNLOADED cross-package sub-pipe, the sliced sweep records it SKIPPED. The result
        # must report that real status — not a flattened SUCCESS — and only the requested slice.
        result = asyncio.run(
            validate_pipe_in_bundle_core(
                bundle_path=cross_package_controller_dir / "bundle.mthds",
                pipe_code="cross_parallel",
                library_dirs=[cross_package_controller_dir],
            )
        )
        assert result["success"] is True
        statuses = {entry["pipe_ref"]: entry["status"] for entry in result["validated_pipes"]}
        # Identity is the namespaced pipe_ref (domain.code), not the bare code.
        assert statuses == {"slice_xpkg.cross_parallel": "SKIPPED"}
        # This bundle has no PipeSignature pipes, so it is runnable — the envelope reports it.
        assert result["pending_signatures"] == []
        assert result["is_runnable"] is True
