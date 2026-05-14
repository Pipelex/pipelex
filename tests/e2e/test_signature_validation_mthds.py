from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.dry_run import DryRunStatus
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_signature.exceptions import PipeSignatureNotExecutableError, SignaturesNotAllowedError
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexRunner
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "signature_bundles"
_SIGNATURE_ONLY = _FIXTURE_DIR / "signature_only.mthds"
_MIXED = _FIXTURE_DIR / "mixed_with_signature_step.mthds"
_MULTIPLICITY = _FIXTURE_DIR / "multi_input_multiplicity.mthds"


@pytest.mark.asyncio
class TestSignatureValidationE2E:
    async def test_signature_only_bundle_strict_fails(self) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=_SIGNATURE_ONLY)
        sig_error = exc_info.value.signature_check_error
        assert sig_error is not None
        assert isinstance(sig_error, SignaturesNotAllowedError)
        assert "signature_demo.summarize_doc" in sig_error.signature_refs

    async def test_signature_only_bundle_lenient_passes(self) -> None:
        result = await validate_bundle(mthds_file_path=_SIGNATURE_ONLY, allow_signatures=True)
        assert "signature_demo.summarize_doc" in result.dry_run_result
        assert result.dry_run_result["signature_demo.summarize_doc"].status is DryRunStatus.SUCCESS

    async def test_mixed_bundle_strict_fails_with_dep_path(self) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=_MIXED)
        sig_error = exc_info.value.signature_check_error
        assert sig_error is not None
        signature_ref = "signature_mixed.summarize_extracted"
        assert signature_ref in sig_error.signature_refs
        assert signature_ref in sig_error.dep_paths
        chain = sig_error.dep_paths[signature_ref]
        assert "signature_mixed.process_doc" in chain

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

    async def test_live_run_signature_pipeline_fails(self) -> None:
        runner = PipelexRunner(
            library_dirs=[str(_FIXTURE_DIR)],
            pipe_run_mode=PipeRunMode.LIVE,
        )
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute_pipeline(
                pipe_code="summarize_doc",
                inputs={"doc": TextContent(text="A document to summarize.")},
            )
        cause = exc_info.value.__cause__
        assert isinstance(cause, PipeSignatureNotExecutableError)
        assert cause.pipe_ref.endswith("summarize_doc")
