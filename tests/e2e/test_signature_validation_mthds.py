from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_signature.exceptions import PipeSignatureNotExecutableError
from pipelex.pipeline.bundle_validator import DryRunStatus
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "signature_bundles"
_SIGNATURE_ONLY = _FIXTURE_DIR / "signature_only.mthds"
_MIXED = _FIXTURE_DIR / "mixed_with_signature_step.mthds"
_MULTIPLICITY = _FIXTURE_DIR / "multi_input_multiplicity.mthds"
_STRUCTURED = _FIXTURE_DIR / "signature_with_structured_output.mthds"


@pytest.mark.asyncio(loop_scope="class")
class TestSignatureValidationE2E:
    async def test_signature_only_bundle_strict_reports_pending(self) -> None:
        # Signatures are never an error (D-B): strict validation does not raise — it reports the
        # outstanding signature via pending_signatures and excludes the signature pipe from the sweep.
        result = await validate_bundle(mthds_file_path=_SIGNATURE_ONLY)
        assert "signature_demo.summarize_doc" in result.pending_signatures
        assert "signature_demo.summarize_doc" not in result.dry_run_result

    async def test_signature_only_bundle_lenient_passes(self) -> None:
        result = await validate_bundle(mthds_file_path=_SIGNATURE_ONLY, allow_signatures=True)
        assert "signature_demo.summarize_doc" in result.dry_run_result
        assert result.dry_run_result["signature_demo.summarize_doc"].status is DryRunStatus.SUCCESS
        # The placeholder is still an unsatisfied forward declaration even when mock-run in lenient mode.
        assert "signature_demo.summarize_doc" in result.pending_signatures

    async def test_mixed_bundle_strict_reports_pending_signature(self) -> None:
        # Strict mode no longer raises on the reached signature. The non-signature caller (process_doc)
        # is still swept and dry-runs trivially (its signature sub-pipe mints a mock); the signature pipe
        # itself is excluded from the sweep and reported via pending_signatures.
        result = await validate_bundle(mthds_file_path=_MIXED)
        assert "signature_mixed.summarize_extracted" in result.pending_signatures
        assert result.dry_run_result["signature_mixed.process_doc"].status is DryRunStatus.SUCCESS
        assert "signature_mixed.summarize_extracted" not in result.dry_run_result

    async def test_mixed_bundle_lenient_passes_and_produces_mock(self) -> None:
        result = await validate_bundle(mthds_file_path=_MIXED, allow_signatures=True)
        process_doc_output = result.dry_run_result.get("signature_mixed.process_doc")
        assert process_doc_output is not None
        assert process_doc_output.status is DryRunStatus.SUCCESS
        # The signature step itself is also dry-run as a SUCCESS
        sig_step_output = result.dry_run_result.get("signature_mixed.summarize_extracted")
        assert sig_step_output is not None
        assert sig_step_output.status is DryRunStatus.SUCCESS

    async def test_multiplicity_inputs_lenient_passes(self) -> None:
        result = await validate_bundle(mthds_file_path=_MULTIPLICITY, allow_signatures=True)
        sig_output = result.dry_run_result.get("signature_multiplicity.fuse_docs_and_images")
        assert sig_output is not None
        assert sig_output.status is DryRunStatus.SUCCESS

    async def test_structured_output_signature_lenient_passes(self) -> None:
        # A signature whose declared output is a custom STRUCTURED concept (fields, not plain Text)
        # exercises the real make_mock_content/polyfactory minting path during the lenient dry-run —
        # the path hardened so a polyfactory failure surfaces as a FAILURE instead of a raw traceback.
        result = await validate_bundle(mthds_file_path=_STRUCTURED, allow_signatures=True)
        sig_output = result.dry_run_result.get("signature_structured.summarize_structured")
        assert sig_output is not None
        assert sig_output.status is DryRunStatus.SUCCESS
        # Prove polyfactory minted the structured class rather than the TextContent fallback: the
        # loaded signature's output concept resolves to a generated structure class. structure_class_name
        # lives on the concept object, so it survives validate_bundle's library teardown.
        sig_pipe = next(pipe for pipe in result.pipes if pipe.code == "summarize_structured")
        assert sig_pipe.output.concept.structure_class_name != "TextContent"

    async def test_live_run_signature_pipeline_fails(self) -> None:
        runner = PipelexMTHDSProtocol(
            library_dirs=[str(_FIXTURE_DIR)],
            pipe_run_mode=PipeRunMode.LIVE,
        )
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(
                pipe_code="summarize_doc",
                inputs={"doc": TextContent(text="A document to summarize.")},
            )
        cause = exc_info.value.__cause__
        assert isinstance(cause, PipeSignatureNotExecutableError)
        assert cause.pipe_ref.endswith("summarize_doc")
