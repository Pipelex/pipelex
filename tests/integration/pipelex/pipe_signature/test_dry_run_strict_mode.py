from typing import Callable

import pytest

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.language.mthds_factory import MthdsFactory
from pipelex.method_hub import get_current_library, get_pipe_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipe_signature.conftest import SIGNATURES_DOMAIN_CODE


def _make_bundle_with_signature() -> PipelexBundleBlueprint:
    return PipelexBundleBlueprint(
        domain="bundle_strict_domain",
        description="Bundle containing a signature reachable from a sequence.",
        concept={
            "BundleDoc": ConceptBlueprint(description="A document for bundle tests."),
            "BundleSummary": ConceptBlueprint(description="A summary for bundle tests."),
        },
        pipe={
            "bundle_sig_step": PipeSignatureBlueprint(
                description="Signature step inside bundle.",
                inputs={"doc": "BundleDoc"},
                output="BundleSummary",
            ),
            "bundle_seq": PipeSequenceBlueprint(
                description="Sequence step calling the signature.",
                inputs={"doc": "BundleDoc"},
                output="BundleSummary",
                steps=[SubPipeBlueprint(pipe="bundle_sig_step", result="summary")],
            ),
        },
    )


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunStrictMode:
    """Signatures are never an error (D-B): strict validation never raises on a reached signature.

    ``allow_signatures`` is a sweep-mechanics flag, not a verdict: in strict mode signature pipes are
    excluded from the dry-run sweep (absent from the returned status map / ``validated_pipes``); a
    non-signature caller that reaches a signature is still swept and dry-runs trivially (the signature
    sub-pipe mints a mock). The unsatisfied set is reported library-wide via ``pending_signatures`` at
    the ``validate_bundle`` level; the "is this a failure?" decision is the consumer's.
    """

    async def test_strict_default_passes_when_no_signatures(
        self,
        setup_signature_library: Callable[[], None],
    ) -> None:
        setup_signature_library()
        step_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="strict_real_step",
            blueprint=PipeLLMBlueprint(
                description="Real LLM step",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                prompt="Summarize $doc.",
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=step_pipe)

        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="strict_real_seq",
            blueprint=PipeSequenceBlueprint(
                description="Pure-operator sequence.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="strict_real_step", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        results = await BundleValidator().validate_pipes([seq_pipe], library_id=get_current_library())
        assert results[seq_pipe.pipe_ref].status is DryRunStatus.SUCCESS

    async def test_strict_sweeps_caller_but_excludes_signature(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # Strict mode does not raise on the reached signature. The signature pipe is excluded from the
        # sweep (absent from the status map); the sequence that reaches it is still swept and SUCCEEDS
        # (the signature sub-pipe mints a mock during the dry run).
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="strict_sig_step",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)
        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="strict_seq_with_sig",
            blueprint=PipeSequenceBlueprint(
                description="Sequence containing a signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="strict_sig_step", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        results = await BundleValidator().validate_pipes([sig_pipe, seq_pipe], library_id=get_current_library())
        assert results[seq_pipe.pipe_ref].status is DryRunStatus.SUCCESS
        # The signature pipe itself is excluded from the strict sweep — never an error, never SUCCESS.
        assert sig_pipe.pipe_ref not in results

    async def test_lenient_succeeds_on_signature_in_sequence(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="lenient_sig_step",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)
        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="lenient_seq_with_sig",
            blueprint=PipeSequenceBlueprint(
                description="Sequence with a signature, but lenient mode.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="lenient_sig_step", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        results = await BundleValidator().validate_pipes([seq_pipe], library_id=get_current_library(), allow_signatures=True)
        assert results[seq_pipe.pipe_ref].status is DryRunStatus.SUCCESS

    async def test_lone_signature_excluded_in_strict_but_swept_in_lenient(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # A signature validated on its own: excluded from the strict sweep (empty status map), but
        # mock-run as a SUCCESS in lenient mode (allow_signatures is sweep mechanics).
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="lone_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        strict_results = await BundleValidator().validate_pipes([sig_pipe], library_id=get_current_library())
        assert strict_results == {}

        lenient_results = await BundleValidator().validate_pipes([sig_pipe], library_id=get_current_library(), allow_signatures=True)
        assert lenient_results[sig_pipe.pipe_ref].status is DryRunStatus.SUCCESS

    async def test_validate_bundle_strict_reports_pending_signature(self) -> None:
        # Strict validate_bundle no longer raises: it returns a result whose library-wide
        # pending_signatures lists the unsatisfied signature, while the non-signature caller is swept.
        mthds_content = MthdsFactory.make_mthds_content(blueprint=_make_bundle_with_signature())
        result = await validate_bundle(mthds_contents=[mthds_content])
        assert "bundle_strict_domain.bundle_sig_step" in result.pending_signatures
        assert result.dry_run_result["bundle_strict_domain.bundle_seq"].status is DryRunStatus.SUCCESS
        # The signature pipe itself is excluded from the strict sweep.
        assert "bundle_strict_domain.bundle_sig_step" not in result.dry_run_result

    async def test_validate_bundle_lenient_passes_on_signature(self) -> None:
        mthds_content = MthdsFactory.make_mthds_content(blueprint=_make_bundle_with_signature())
        result = await validate_bundle(mthds_contents=[mthds_content], allow_signatures=True)
        assert "bundle_strict_domain.bundle_sig_step" in result.dry_run_result
        assert "bundle_strict_domain.bundle_seq" in result.dry_run_result
        for entry in result.dry_run_result.values():
            assert entry.status is DryRunStatus.SUCCESS
        # The placeholder is still an unsatisfied forward declaration even when mock-run.
        assert "bundle_strict_domain.bundle_sig_step" in result.pending_signatures
