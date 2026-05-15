from typing import Callable

import pytest

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_pipe_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.dry_run import DryRunStatus, dry_run_pipe, dry_run_pipes
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
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

        result = await dry_run_pipe(seq_pipe)
        assert result.status is DryRunStatus.SUCCESS

    async def test_strict_fails_on_signature_in_sequence(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
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

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipe(seq_pipe)
        assert sig_pipe.pipe_ref in exc_info.value.signature_refs

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

        result = await dry_run_pipe(seq_pipe, allow_signatures=True)
        assert result.status is DryRunStatus.SUCCESS

    async def test_strict_error_lists_all_signatures(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_a = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="multi_sig_a",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        sig_b = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="multi_sig_b",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[sig_a, sig_b])

        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="seq_multi_sig",
            blueprint=PipeSequenceBlueprint(
                description="Sequence containing two signatures.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[
                    SubPipeBlueprint(pipe="multi_sig_a", result="summary_a"),
                    SubPipeBlueprint(pipe="multi_sig_b", result="summary_b"),
                ],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipe(seq_pipe)
        assert exc_info.value.signature_refs == {sig_a.pipe_ref, sig_b.pipe_ref}

    async def test_strict_error_includes_dep_paths(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="dep_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)
        inner_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="dep_inner_seq",
            blueprint=PipeSequenceBlueprint(
                description="Inner sequence wrapping the signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="dep_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=inner_seq)
        outer_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="dep_outer_seq",
            blueprint=PipeSequenceBlueprint(
                description="Outer sequence calling inner sequence.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="dep_inner_seq", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=outer_seq)

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipe(outer_seq)
        error = exc_info.value
        assert sig_pipe.pipe_ref in error.dep_paths
        chain = error.dep_paths[sig_pipe.pipe_ref]
        assert outer_seq.pipe_ref in chain
        assert inner_seq.pipe_ref in chain
        for entry in chain:
            assert "." in entry, f"dep chain entries must be qualified pipe_refs, got: {entry}"

    async def test_validate_bundle_strict_fails_on_signature(self) -> None:
        bundle = _make_bundle_with_signature()
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(blueprints=[bundle])
        sig_error = exc_info.value.signature_check_error
        assert sig_error is not None
        assert "bundle_strict_domain.bundle_sig_step" in sig_error.signature_refs
        assert "bundle_strict_domain.bundle_sig_step" in sig_error.dep_paths

    async def test_dry_run_pipes_aggregates_signatures_across_pipes(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # Regression: when multiple pipes in the batch each reach distinct signatures, the strict
        # pre-check must surface every offender in a single error, not short-circuit on the first.
        setup_signature_library()
        sig_a = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="agg_sig_a",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        sig_b = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="agg_sig_b",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[sig_a, sig_b])

        seq_a = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="agg_seq_a",
            blueprint=PipeSequenceBlueprint(
                description="Sequence reaching sig_a.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="agg_sig_a", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        seq_b = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="agg_seq_b",
            blueprint=PipeSequenceBlueprint(
                description="Sequence reaching sig_b.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="agg_sig_b", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[seq_a, seq_b])

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipes(pipes=[seq_a, seq_b])
        # Both signatures must appear — not just the one from the first pipe.
        assert exc_info.value.signature_refs == {sig_a.pipe_ref, sig_b.pipe_ref}

    async def test_validate_bundle_lenient_passes_on_signature(self) -> None:
        bundle = _make_bundle_with_signature()
        result = await validate_bundle(blueprints=[bundle], allow_signatures=True)
        assert "bundle_strict_domain.bundle_sig_step" in result.dry_run_result
        assert "bundle_strict_domain.bundle_seq" in result.dry_run_result
        for entry in result.dry_run_result.values():
            assert entry.status is DryRunStatus.SUCCESS

    async def test_aggregated_error_names_actual_offender_not_first_pipe(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # Regression: when pipes[0] is clean and a later pipe reaches a signature, the aggregated
        # error must name the offender — not pipes[0]. The previous code used pipes[0].pipe_ref
        # unconditionally for the message header.
        setup_signature_library()
        innocent_op = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="innocent_first_op",
            blueprint=PipeLLMBlueprint(
                description="Real LLM step with no signature deps.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                prompt="Summarize $doc.",
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=innocent_op)

        hidden_sig = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="hidden_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=hidden_sig)
        offender_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="offender_seq",
            blueprint=PipeSequenceBlueprint(
                description="Sequence reaching a signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="hidden_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=offender_seq)

        # Iterate innocent FIRST, offender SECOND — exposes the pipes[0] bug.
        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipes(pipes=[innocent_op, offender_seq])
        error = exc_info.value
        assert offender_seq.pipe_ref in error.offending_pipe_refs
        assert innocent_op.pipe_ref not in error.offending_pipe_refs
        assert offender_seq.pipe_ref in str(error)
        assert f"'{innocent_op.pipe_ref}' depends on" not in str(error)

    async def test_aggregated_error_lists_all_offenders_when_multiple(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # Regression: when multiple pipes each reach distinct signatures, all offenders must be
        # reported — not just one. Multi-offender message uses a plural header.
        setup_signature_library()
        sig_a = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="multi_off_sig_a",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        sig_b = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="multi_off_sig_b",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[sig_a, sig_b])
        seq_a = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="multi_off_seq_a",
            blueprint=PipeSequenceBlueprint(
                description="Sequence reaching sig_a.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="multi_off_sig_a", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        seq_b = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="multi_off_seq_b",
            blueprint=PipeSequenceBlueprint(
                description="Sequence reaching sig_b.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="multi_off_sig_b", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[seq_a, seq_b])

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipes(pipes=[seq_a, seq_b])
        error = exc_info.value
        assert error.offending_pipe_refs == {seq_a.pipe_ref, seq_b.pipe_ref}
        message = str(error)
        assert "The following pipes depend on" in message
        assert seq_a.pipe_ref in message
        assert seq_b.pipe_ref in message

    async def test_lone_signature_not_listed_as_offender(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # A signature validated on its own is the placeholder itself, not a pipe that
        # "depends on" one: it belongs in signature_refs, never in offending_pipe_refs.
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="lone_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipe(sig_pipe)
        error = exc_info.value
        assert sig_pipe.pipe_ref in error.signature_refs
        assert sig_pipe.pipe_ref not in error.offending_pipe_refs
        assert error.offending_pipe_refs == set()
        assert "Validation found PipeSignature placeholders" in str(error)

    async def test_dry_run_pipes_excludes_signature_from_offenders(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # When the pipe list contains both a signature and a controller that reaches it,
        # only the controller is an offender — the signature is the placeholder itself.
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="listed_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)
        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="listed_seq",
            blueprint=PipeSequenceBlueprint(
                description="Sequence calling the signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="listed_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        with pytest.raises(SignaturesNotAllowedError) as exc_info:
            await dry_run_pipes(pipes=[sig_pipe, seq_pipe])
        error = exc_info.value
        assert error.offending_pipe_refs == {seq_pipe.pipe_ref}
        assert sig_pipe.pipe_ref not in error.offending_pipe_refs
        assert sig_pipe.pipe_ref in error.signature_refs
