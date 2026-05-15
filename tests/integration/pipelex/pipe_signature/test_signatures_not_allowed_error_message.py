from typing import Callable

from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_optional_pipe, get_pipe_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from tests.integration.pipelex.pipe_signature.conftest import SIGNATURES_DOMAIN_CODE


class TestSignaturesNotAllowedErrorMessage:
    def _build_sequence_with_signature(
        self,
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> tuple[PipeSignature, PipeSequence]:
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="msg_inner_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        inner_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="msg_inner_seq",
            blueprint=PipeSequenceBlueprint(
                description="Inner sequence wrapping the signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="msg_inner_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=inner_seq)

        outer_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="msg_outer_seq",
            blueprint=PipeSequenceBlueprint(
                description="Outer sequence calling the inner sequence.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="msg_inner_seq", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=outer_seq)
        return sig_pipe, outer_seq

    def test_dep_paths_keys_are_qualified_pipe_refs(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe, outer_seq = self._build_sequence_with_signature(make_signature_blueprint)

        error = SignaturesNotAllowedError(
            offending_pipe_refs={outer_seq.pipe_ref},
            signature_refs=outer_seq.collect_signature_refs(pipe_lookup=get_optional_pipe),
            dep_paths=outer_seq.collect_signature_paths(pipe_lookup=get_optional_pipe),
        )
        assert sig_pipe.pipe_ref in error.dep_paths
        for key in error.dep_paths:
            assert "." in key, f"dep_paths keys must be qualified pipe_refs, got: {key}"
        dep_chain = error.dep_paths[sig_pipe.pipe_ref]
        assert outer_seq.pipe_ref in dep_chain
        for entry in dep_chain:
            assert "." in entry, f"dep_paths values must list qualified pipe_refs, got: {entry}"

    def test_message_lists_each_signature_with_dep_path(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe, outer_seq = self._build_sequence_with_signature(make_signature_blueprint)

        error = SignaturesNotAllowedError(
            offending_pipe_refs={outer_seq.pipe_ref},
            signature_refs=outer_seq.collect_signature_refs(pipe_lookup=get_optional_pipe),
            dep_paths=outer_seq.collect_signature_paths(pipe_lookup=get_optional_pipe),
        )
        message = str(error)
        assert sig_pipe.pipe_ref in message
        assert outer_seq.pipe_ref in message

    def test_message_includes_fix_suggestion(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe, outer_seq = self._build_sequence_with_signature(make_signature_blueprint)

        error = SignaturesNotAllowedError(
            offending_pipe_refs={outer_seq.pipe_ref},
            signature_refs=outer_seq.collect_signature_refs(pipe_lookup=get_optional_pipe),
            dep_paths=outer_seq.collect_signature_paths(pipe_lookup=get_optional_pipe),
        )
        message = str(error)
        assert "--allow-signatures" in message
        assert "real" in message.lower() or "implement" in message.lower()
        assert sig_pipe.pipe_ref in message
