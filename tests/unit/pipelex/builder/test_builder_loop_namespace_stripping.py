import pytest

from pipelex.builder.builder_loop import BuilderLoop
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome


def _make_bundle(
    domain: str = "scoring",
    main_pipe: str = "main",
    pipes: dict[str, PipeSpecUnion] | None = None,
) -> PipelexBundleSpec:
    """Create a minimal PipelexBundleSpec for namespace stripping tests."""
    return PipelexBundleSpec.model_construct(
        domain=domain,
        main_pipe=main_pipe,
        concept={},
        pipe=pipes or {},
    )


class TestBuilderLoopNamespaceStripping:
    """Tests for _strip_namespace_from_pipe_codes and _strip_dotted_pipe_code in BuilderLoop."""

    # --- Tests for _strip_dotted_pipe_code ---

    @pytest.mark.parametrize(
        ("pipe_code", "expected"),
        [
            ("my_pipe", "my_pipe"),
            ("foo.my_pipe", "my_pipe"),
            ("a.b.my_pipe", "my_pipe"),
            ("scoring.compute_score", "compute_score"),
        ],
    )
    def test_strip_dotted_pipe_code(self, pipe_code: str, expected: str) -> None:
        """Verify _strip_dotted_pipe_code extracts bare code after last dot."""
        result = BuilderLoop._strip_dotted_pipe_code(pipe_code)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result == expected

    # --- Tests for pipe dict key stripping ---

    def test_dotted_pipe_key_is_stripped(self) -> None:
        """A dotted pipe dict key 'foo.my_pipe' should be stripped to 'my_pipe'."""
        bundle = _make_bundle(
            main_pipe="my_pipe",
            pipes={
                "foo.my_pipe": PipeLLMSpec.model_construct(
                    pipe_code="foo.my_pipe",
                    description="A pipe",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Do stuff",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        assert "my_pipe" in result.pipe
        assert "foo.my_pipe" not in result.pipe

    def test_multi_segment_dotted_key_is_stripped(self) -> None:
        """A multi-segment dotted key 'a.b.my_pipe' should be stripped to 'my_pipe'."""
        bundle = _make_bundle(
            main_pipe="my_pipe",
            pipes={
                "a.b.my_pipe": PipeLLMSpec.model_construct(
                    pipe_code="a.b.my_pipe",
                    description="A pipe",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Do stuff",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        assert "my_pipe" in result.pipe
        assert "a.b.my_pipe" not in result.pipe

    def test_bare_snake_case_key_passes_through(self) -> None:
        """A bare snake_case key should pass through unchanged."""
        bundle = _make_bundle(
            main_pipe="compute_score",
            pipes={
                "compute_score": PipeLLMSpec.model_construct(
                    pipe_code="compute_score",
                    description="A pipe",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Do stuff",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        assert "compute_score" in result.pipe

    # --- Tests for main_pipe stripping ---

    def test_main_pipe_with_dot_prefix_is_stripped(self) -> None:
        """main_pipe with a dot prefix should be stripped."""
        bundle = _make_bundle(
            main_pipe="scoring.main_sequence",
            pipes={
                "main_sequence": PipeLLMSpec.model_construct(
                    pipe_code="main_sequence",
                    description="Main",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Do stuff",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.main_pipe == "main_sequence"

    # --- Tests for PipeSpec.pipe_code stripping ---

    def test_pipe_code_field_with_dot_is_stripped(self) -> None:
        """PipeSpec.pipe_code with a dot prefix should be stripped."""
        bundle = _make_bundle(
            main_pipe="my_pipe",
            pipes={
                "scoring.my_pipe": PipeLLMSpec.model_construct(
                    pipe_code="scoring.my_pipe",
                    description="A pipe",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Do stuff",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        pipe_spec = result.pipe["my_pipe"]
        assert pipe_spec.pipe_code == "my_pipe"

    # --- Tests for PipeBatchSpec.branch_pipe_code stripping ---

    def test_batch_branch_pipe_code_with_dot_is_stripped(self) -> None:
        """PipeBatchSpec.branch_pipe_code with a dot prefix should be stripped."""
        bundle = _make_bundle(
            main_pipe="batch_pipe",
            pipes={
                "batch_pipe": PipeBatchSpec.model_construct(
                    pipe_code="batch_pipe",
                    description="Batch",
                    type="PipeBatch",
                    pipe_category="PipeController",
                    inputs={"items": "Text[]"},
                    output="Text[]",
                    branch_pipe_code="scoring.process_item",
                    input_list_name="items",
                    input_item_name="item",
                ),
                "process_item": PipeLLMSpec.model_construct(
                    pipe_code="process_item",
                    description="Process",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={"item": "Text"},
                    output="Text",
                    model="$retrieval",
                    prompt="Process @item",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        batch_spec = result.pipe["batch_pipe"]
        assert isinstance(batch_spec, PipeBatchSpec)
        assert batch_spec.branch_pipe_code == "process_item"

    # --- Tests for PipeSequenceSpec.steps stripping ---

    def test_sequence_step_pipe_code_with_dot_is_stripped(self) -> None:
        """PipeSequenceSpec.steps[*].pipe_code with a dot prefix should be stripped."""
        bundle = _make_bundle(
            main_pipe="main_seq",
            pipes={
                "main_seq": PipeSequenceSpec.model_construct(
                    pipe_code="main_seq",
                    description="Sequence",
                    type="PipeSequence",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    steps=[
                        SubPipeSpec(pipe_code="scoring.step_one", result="result_one"),
                        SubPipeSpec(pipe_code="step_two", result="result_two"),
                    ],
                ),
                "step_one": PipeLLMSpec.model_construct(
                    pipe_code="step_one",
                    description="Step one",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Step 1",
                ),
                "step_two": PipeLLMSpec.model_construct(
                    pipe_code="step_two",
                    description="Step two",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Step 2",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        seq_spec = result.pipe["main_seq"]
        assert isinstance(seq_spec, PipeSequenceSpec)
        assert seq_spec.steps[0].pipe_code == "step_one"
        assert seq_spec.steps[1].pipe_code == "step_two"

    # --- Tests for PipeParallelSpec.branches stripping ---

    def test_parallel_branch_pipe_code_with_dot_is_stripped(self) -> None:
        """PipeParallelSpec.branches[*].pipe_code with a dot prefix should be stripped."""
        bundle = _make_bundle(
            main_pipe="main_par",
            pipes={
                "main_par": PipeParallelSpec.model_construct(
                    pipe_code="main_par",
                    description="Parallel",
                    type="PipeParallel",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    branches=[
                        SubPipeSpec(pipe_code="scoring.branch_a", result="result_a"),
                        SubPipeSpec(pipe_code="branch_b", result="result_b"),
                    ],
                    add_each_output=True,
                    combined_output=None,
                ),
                "branch_a": PipeLLMSpec.model_construct(
                    pipe_code="branch_a",
                    description="Branch A",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Branch A",
                ),
                "branch_b": PipeLLMSpec.model_construct(
                    pipe_code="branch_b",
                    description="Branch B",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Branch B",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        par_spec = result.pipe["main_par"]
        assert isinstance(par_spec, PipeParallelSpec)
        assert par_spec.branches[0].pipe_code == "branch_a"
        assert par_spec.branches[1].pipe_code == "branch_b"

    # --- Tests for PipeConditionSpec stripping ---

    def test_condition_outcomes_with_dot_are_stripped(self) -> None:
        """PipeConditionSpec outcomes values with dot prefixes should be stripped."""
        bundle = _make_bundle(
            main_pipe="main_cond",
            pipes={
                "main_cond": PipeConditionSpec.model_construct(
                    pipe_code="main_cond",
                    description="Condition",
                    type="PipeCondition",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    jinja2_expression_template="{{ status }}",
                    outcomes={
                        "good": "scoring.handle_good",
                        "bad": "scoring.handle_bad",
                    },
                    default_outcome="scoring.handle_default",
                ),
                "handle_good": PipeLLMSpec.model_construct(
                    pipe_code="handle_good",
                    description="Handle good",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Good",
                ),
                "handle_bad": PipeLLMSpec.model_construct(
                    pipe_code="handle_bad",
                    description="Handle bad",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Bad",
                ),
                "handle_default": PipeLLMSpec.model_construct(
                    pipe_code="handle_default",
                    description="Handle default",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Default",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        cond_spec = result.pipe["main_cond"]
        assert isinstance(cond_spec, PipeConditionSpec)
        assert cond_spec.outcomes["good"] == "handle_good"
        assert cond_spec.outcomes["bad"] == "handle_bad"
        assert cond_spec.default_outcome == "handle_default"

    def test_condition_special_outcomes_are_left_intact(self) -> None:
        """SpecialOutcome values ('fail', 'continue') in condition outcomes should not be stripped."""
        bundle = _make_bundle(
            main_pipe="main_cond",
            pipes={
                "main_cond": PipeConditionSpec.model_construct(
                    pipe_code="main_cond",
                    description="Condition",
                    type="PipeCondition",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    jinja2_expression_template="{{ status }}",
                    outcomes={
                        "good": "scoring.handle_good",
                        "bad": SpecialOutcome.FAIL,
                        "neutral": SpecialOutcome.CONTINUE,
                    },
                    default_outcome=SpecialOutcome.FAIL,
                ),
                "handle_good": PipeLLMSpec.model_construct(
                    pipe_code="handle_good",
                    description="Handle good",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Good",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        cond_spec = result.pipe["main_cond"]
        assert isinstance(cond_spec, PipeConditionSpec)
        assert cond_spec.outcomes["good"] == "handle_good"
        assert cond_spec.outcomes["bad"] == SpecialOutcome.FAIL
        assert cond_spec.outcomes["neutral"] == SpecialOutcome.CONTINUE
        assert cond_spec.default_outcome == SpecialOutcome.FAIL

    # --- Tests for cross-domain references left intact ---

    def test_cross_domain_sequence_step_not_stripped(self) -> None:
        """A dotted reference whose bare code is NOT defined in the bundle should be left intact."""
        bundle = _make_bundle(
            main_pipe="main_seq",
            pipes={
                "main_seq": PipeSequenceSpec.model_construct(
                    pipe_code="main_seq",
                    description="Sequence",
                    type="PipeSequence",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    steps=[
                        SubPipeSpec(pipe_code="other_domain.external_pipe", result="ext_result"),
                        SubPipeSpec(pipe_code="scoring.local_pipe", result="loc_result"),
                    ],
                ),
                "local_pipe": PipeLLMSpec.model_construct(
                    pipe_code="local_pipe",
                    description="Local",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Local",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        seq_spec = result.pipe["main_seq"]
        assert isinstance(seq_spec, PipeSequenceSpec)
        # external_pipe is NOT defined in the bundle → reference left intact
        assert seq_spec.steps[0].pipe_code == "other_domain.external_pipe"
        # local_pipe IS defined in the bundle → reference stripped
        assert seq_spec.steps[1].pipe_code == "local_pipe"

    def test_cross_domain_condition_outcome_not_stripped(self) -> None:
        """A dotted condition outcome whose bare code is NOT in the bundle should be left intact."""
        bundle = _make_bundle(
            main_pipe="main_cond",
            pipes={
                "main_cond": PipeConditionSpec.model_construct(
                    pipe_code="main_cond",
                    description="Condition",
                    type="PipeCondition",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    jinja2_expression_template="{{ status }}",
                    outcomes={
                        "local": "scoring.handle_local",
                        "external": "other_domain.handle_external",
                    },
                    default_outcome="other_domain.handle_fallback",
                ),
                "handle_local": PipeLLMSpec.model_construct(
                    pipe_code="handle_local",
                    description="Handle local",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Local",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        cond_spec = result.pipe["main_cond"]
        assert isinstance(cond_spec, PipeConditionSpec)
        # handle_local IS in bundle → stripped
        assert cond_spec.outcomes["local"] == "handle_local"
        # handle_external is NOT in bundle → left intact
        assert cond_spec.outcomes["external"] == "other_domain.handle_external"
        # handle_fallback is NOT in bundle → left intact
        assert cond_spec.default_outcome == "other_domain.handle_fallback"

    def test_cross_domain_batch_branch_not_stripped(self) -> None:
        """A dotted batch branch_pipe_code whose bare code is NOT in the bundle should be left intact."""
        bundle = _make_bundle(
            main_pipe="batch_pipe",
            pipes={
                "batch_pipe": PipeBatchSpec.model_construct(
                    pipe_code="batch_pipe",
                    description="Batch",
                    type="PipeBatch",
                    pipe_category="PipeController",
                    inputs={"items": "Text[]"},
                    output="Text[]",
                    branch_pipe_code="other_domain.external_process",
                    input_list_name="items",
                    input_item_name="item",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.pipe is not None
        batch_spec = result.pipe["batch_pipe"]
        assert isinstance(batch_spec, PipeBatchSpec)
        # external_process is NOT in the bundle → left intact
        assert batch_spec.branch_pipe_code == "other_domain.external_process"

    # --- Test for no-op on clean bundle ---

    def test_clean_bundle_passes_through_unchanged(self) -> None:
        """A bundle with no dotted pipe codes should pass through unchanged."""
        bundle = _make_bundle(
            main_pipe="main_seq",
            pipes={
                "main_seq": PipeSequenceSpec.model_construct(
                    pipe_code="main_seq",
                    description="Sequence",
                    type="PipeSequence",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    steps=[
                        SubPipeSpec(pipe_code="step_one", result="result_one"),
                    ],
                ),
                "step_one": PipeLLMSpec.model_construct(
                    pipe_code="step_one",
                    description="Step one",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    model="$retrieval",
                    prompt="Step 1",
                ),
            },
        )

        result = BuilderLoop._strip_namespace_from_pipe_codes(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.main_pipe == "main_seq"
        assert result.pipe is not None
        assert set(result.pipe.keys()) == {"main_seq", "step_one"}
        seq_spec = result.pipe["main_seq"]
        assert isinstance(seq_spec, PipeSequenceSpec)
        assert seq_spec.steps[0].pipe_code == "step_one"
