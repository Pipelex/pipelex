from typing import Callable

from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.pipe_signature.signature_walk import collect_signature_paths, collect_signature_refs
from tests.integration.pipelex.pipe_signature.conftest import SIGNATURES_DOMAIN_CODE


class TestCollectSignatureRefs:
    def test_operator_returns_empty(
        self,
        setup_signature_library: Callable[[], None],
    ) -> None:
        setup_signature_library()
        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="operator_pipe",
            blueprint=PipeLLMBlueprint(
                description="An operator with no sub-pipes.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                prompt="Summarize $doc.",
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        assert collect_signature_refs(pipe=pipe_llm) == set()

    def test_signature_returns_self(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="self_signature",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        assert collect_signature_refs(pipe=runtime) == {runtime.pipe_ref}

    def test_controller_sequence_walks_steps(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="seq_sig_step",
            blueprint=sig_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        seq_blueprint = PipeSequenceBlueprint(
            description="Sequence containing a signature step.",
            inputs={"doc": "SigTestDoc"},
            output="SigTestSummary",
            steps=[SubPipeBlueprint(pipe="seq_sig_step", result="summary")],
        )
        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="seq_with_signature",
            blueprint=seq_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        assert collect_signature_refs(pipe=seq_pipe) == {sig_pipe.pipe_ref}

    def test_controller_parallel_walks_branches(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="par_sig_branch",
            blueprint=sig_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        parallel_blueprint = PipeParallelBlueprint(
            description="Parallel with a signature branch.",
            inputs={"doc": "SigTestDoc"},
            output="SigTestSummary",
            branches=[SubPipeBlueprint(pipe="par_sig_branch", result="summary")],
            add_each_output=True,
        )
        par_pipe = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="par_with_signature",
            blueprint=parallel_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=par_pipe)

        assert collect_signature_refs(pipe=par_pipe) == {sig_pipe.pipe_ref}

    def test_controller_condition_walks_outcomes(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_blueprint_a = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        sig_a = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="cond_sig_a",
            blueprint=sig_blueprint_a,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        sig_blueprint_b = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        sig_b = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="cond_sig_b",
            blueprint=sig_blueprint_b,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[sig_a, sig_b])

        cond_blueprint = PipeConditionBlueprint(
            description="Condition routing to signatures.",
            inputs={"doc": "SigTestDoc"},
            output="SigTestSummary",
            expression="doc",
            outcomes={"A": "cond_sig_a"},
            default_outcome="cond_sig_b",
        )
        cond_pipe = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="cond_with_signatures",
            blueprint=cond_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=cond_pipe)

        assert collect_signature_refs(pipe=cond_pipe) == {sig_a.pipe_ref, sig_b.pipe_ref}

    def test_controller_batch_walks_branch(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="batch_sig_branch",
            blueprint=sig_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        batch_blueprint = PipeBatchBlueprint(
            description="Batch over a signature branch.",
            inputs={"docs": "SigTestDoc[]"},
            output="SigTestSummary[]",
            branch_pipe_code="batch_sig_branch",
            input_list_name="docs",
            input_item_name="doc",
        )
        batch_pipe = PipeFactory[PipeBatch].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="batch_with_signature",
            blueprint=batch_blueprint,
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=batch_pipe)

        assert collect_signature_refs(pipe=batch_pipe) == {sig_pipe.pipe_ref}

    def test_nested_controller_walks_deeply(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="nested_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        inner_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="inner_seq",
            blueprint=PipeSequenceBlueprint(
                description="Inner sequence calling signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="nested_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=inner_seq)

        outer_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="outer_seq",
            blueprint=PipeSequenceBlueprint(
                description="Outer sequence calling inner sequence.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="inner_seq", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=outer_seq)

        assert collect_signature_refs(pipe=outer_seq) == {sig_pipe.pipe_ref}

    def test_cycle_protection(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="cycle_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        # Build a sequence that references itself (a cycle) plus a signature step
        seq_a = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="seq_cycle_a",
            blueprint=PipeSequenceBlueprint(
                description="Sequence that depends on itself.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[
                    SubPipeBlueprint(pipe="cycle_sig", result="summary_via_sig"),
                    SubPipeBlueprint(pipe="seq_cycle_a", result="summary_recurse"),
                ],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_a)

        # Walk terminates and returns the signature reachable through the non-cycle step.
        assert collect_signature_refs(pipe=seq_a) == {sig_pipe.pipe_ref}

    def test_unresolved_cross_package_dep_skipped(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="reachable_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        # Two steps: one is a reachable signature, the other is an unresolved cross-package ref.
        seq_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="seq_with_missing_dep",
            blueprint=PipeSequenceBlueprint(
                description="Sequence with both a real signature and an unresolved cross-package dep.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[
                    SubPipeBlueprint(pipe="reachable_sig", result="summary"),
                    SubPipeBlueprint(pipe="missing_pkg->some.unknown_pipe", result="ignored"),
                ],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_pipe)

        # Unresolved dep is skipped silently; reachable signature is still found.
        assert collect_signature_refs(pipe=seq_pipe) == {sig_pipe.pipe_ref}

    def test_collect_signature_paths_prefers_longest_chain_in_diamond(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # Diamond: a single signature S is reachable from `top` by a short branch (top -> b_seq -> S)
        # and a long branch (top -> c_seq -> d_seq -> S). The short branch sorts first ("b" < "c"),
        # so a first-path-wins walk would record the short chain. The walk must keep the longest.
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="diamond_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        b_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="b_seq",
            blueprint=PipeSequenceBlueprint(
                description="Short branch straight to the signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="diamond_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        d_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="d_seq",
            blueprint=PipeSequenceBlueprint(
                description="Last hop of the long branch before the signature.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="diamond_sig", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_pipes(pipes=[b_seq, d_seq])

        c_seq = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="c_seq",
            blueprint=PipeSequenceBlueprint(
                description="First hop of the long branch.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[SubPipeBlueprint(pipe="d_seq", result="summary")],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=c_seq)

        top = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="diamond_top",
            blueprint=PipeSequenceBlueprint(
                description="Diamond root: short branch then long branch.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[
                    SubPipeBlueprint(pipe="b_seq", result="via_short"),
                    SubPipeBlueprint(pipe="c_seq", result="via_long"),
                ],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=top)

        paths = collect_signature_paths(pipe=top)
        assert paths[sig_pipe.pipe_ref] == [top.pipe_ref, c_seq.pipe_ref, d_seq.pipe_ref]

    def test_collect_signature_paths_breaks_cycles(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # The path walk uses active-path (back-edge) cycle detection; a self-referencing
        # controller must terminate and still record the signature reachable off the cycle.
        setup_signature_library()
        sig_pipe = PipeFactory[PipeSignature].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="paths_cycle_sig",
            blueprint=make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary"),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=sig_pipe)

        seq_a = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=SIGNATURES_DOMAIN_CODE,
            pipe_code="paths_seq_cycle",
            blueprint=PipeSequenceBlueprint(
                description="Sequence that depends on itself plus a signature step.",
                inputs={"doc": "SigTestDoc"},
                output="SigTestSummary",
                steps=[
                    SubPipeBlueprint(pipe="paths_cycle_sig", result="summary_via_sig"),
                    SubPipeBlueprint(pipe="paths_seq_cycle", result="summary_recurse"),
                ],
            ),
            concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
        )
        get_pipe_library().add_new_pipe(pipe=seq_a)

        paths = collect_signature_paths(pipe=seq_a)
        assert sig_pipe.pipe_ref in paths
        assert paths[sig_pipe.pipe_ref] == [seq_a.pipe_ref]
