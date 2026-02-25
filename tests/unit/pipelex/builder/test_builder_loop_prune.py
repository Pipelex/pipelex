import logging

import pytest

from pipelex.builder.builder_loop import BuilderLoop
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec


def _make_bundle_for_prune(
    domain: str = "my_domain",
    main_pipe: str = "main_sequence",
    pipes: dict[str, PipeSpecUnion] | None = None,
    concepts: dict[str, ConceptSpec | str] | None = None,
) -> PipelexBundleSpec:
    """Create a minimal PipelexBundleSpec for testing _prune_unreachable_specs."""
    return PipelexBundleSpec.model_construct(
        domain=domain,
        main_pipe=main_pipe,
        concept=concepts or {},
        pipe=pipes or {},
    )


class TestBuilderLoopPruneUnreachableSpecs:
    """Tests for _prune_unreachable_specs and _extract_local_bare_code in BuilderLoop."""

    # --- Tests for _extract_local_bare_code ---

    @pytest.mark.parametrize(
        ("concept_ref", "domain", "expected"),
        [
            ("Doc", "my_domain", "Doc"),
            ("my_domain.Doc", "my_domain", "Doc"),
            ("external.Doc", "my_domain", None),
            ("other_lib.Foo", "my_domain", None),
            ("my_domain.nested.Thing", "my_domain", None),
        ],
    )
    def test_extract_local_bare_code(self, concept_ref: str, domain: str, expected: str | None) -> None:
        """Verify _extract_local_bare_code returns bare code for local refs and None for external."""
        result = BuilderLoop._extract_local_bare_code(concept_ref_or_code=concept_ref, domain=domain)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert result == expected

    # --- Tests for domain filtering ---

    def test_prune_external_ref_does_not_keep_local(self) -> None:
        """An external reference like 'external.Document' should not prevent local 'Document' from being pruned."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="main_sequence",
            pipes={
                "main_sequence": PipeSequenceSpec.model_construct(
                    pipe_code="main_sequence",
                    description="Main",
                    type="PipeSequence",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    steps=[SubPipeSpec(pipe_code="generate_text", result="text_output")],
                ),
                "generate_text": PipeLLMSpec.model_construct(
                    pipe_code="generate_text",
                    description="Generate text",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={"doc": "external.Document"},
                    output="Text",
                    llm_talent="data-retrieval",
                    prompt="Process @doc",
                ),
            },
            concepts={
                "Document": ConceptSpec(
                    the_concept_code="Document",
                    description="A local document concept that should be pruned",
                    refines="Text",
                ),
            },
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # Document should be pruned because 'external.Document' is an external ref
        assert result.concept is not None
        assert "Document" not in result.concept

    def test_prune_keeps_same_domain_prefixed(self) -> None:
        """A same-domain prefixed reference like 'my_domain.Report' should keep local 'Report'."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="generate_report",
            pipes={
                "generate_report": PipeLLMSpec.model_construct(
                    pipe_code="generate_report",
                    description="Generate report",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="my_domain.Report",
                    llm_talent="data-retrieval",
                    prompt="Generate a report",
                ),
            },
            concepts={
                "Report": ConceptSpec(
                    the_concept_code="Report",
                    description="A report concept",
                    refines="Text",
                ),
            },
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # Report should NOT be pruned because 'my_domain.Report' is a local ref
        assert result.concept is not None
        assert "Report" in result.concept

    def test_prune_keeps_unprefixed_local(self) -> None:
        """An unprefixed reference like 'Summary' should keep local 'Summary'."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="generate_summary",
            pipes={
                "generate_summary": PipeLLMSpec.model_construct(
                    pipe_code="generate_summary",
                    description="Generate summary",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Summary",
                    llm_talent="data-retrieval",
                    prompt="Generate a summary",
                ),
            },
            concepts={
                "Summary": ConceptSpec(
                    the_concept_code="Summary",
                    description="A summary concept",
                    refines="Text",
                ),
            },
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.concept is not None
        assert "Summary" in result.concept

    def test_prune_transitive_external_ref(self) -> None:
        """A concept refining an external ref should not keep the local concept with the same bare name."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="generate_result",
            pipes={
                "generate_result": PipeLLMSpec.model_construct(
                    pipe_code="generate_result",
                    description="Generate result",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Result",
                    llm_talent="data-retrieval",
                    prompt="Generate a result",
                ),
            },
            concepts={
                "Result": ConceptSpec(
                    the_concept_code="Result",
                    description="A result concept",
                    refines="external.Info",
                ),
                "Info": ConceptSpec(
                    the_concept_code="Info",
                    description="A local info concept that should be pruned",
                    refines="Text",
                ),
            },
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.concept is not None
        # Result should be kept (referenced by pipe output)
        assert "Result" in result.concept
        # Info should be pruned because 'external.Info' is external
        assert "Info" not in result.concept

    def test_prune_transitive_local_ref(self) -> None:
        """A concept refining a local concept should keep that concept."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="generate_derived",
            pipes={
                "generate_derived": PipeLLMSpec.model_construct(
                    pipe_code="generate_derived",
                    description="Generate derived",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Derived",
                    llm_talent="data-retrieval",
                    prompt="Generate derived content",
                ),
            },
            concepts={
                "Derived": ConceptSpec(
                    the_concept_code="Derived",
                    description="A derived concept",
                    refines="Base",
                ),
                "Base": ConceptSpec(
                    the_concept_code="Base",
                    description="A base concept",
                    refines="Text",
                ),
            },
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.concept is not None
        assert "Derived" in result.concept
        assert "Base" in result.concept

    def test_prune_transitive_structure_external_ref(self) -> None:
        """A concept with a structure field referencing an external concept should not keep the local bare name."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="generate_container",
            pipes={
                "generate_container": PipeLLMSpec.model_construct(
                    pipe_code="generate_container",
                    description="Generate container",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Container",
                    llm_talent="data-retrieval",
                    prompt="Generate container",
                ),
            },
            concepts={
                "Container": ConceptSpec(
                    the_concept_code="Container",
                    description="A container",
                    structure={
                        "items": ConceptStructureSpec(
                            the_field_name="items",
                            description="Items list",
                            type=ConceptStructureSpecFieldType.LIST,
                            item_type="concept",
                            item_concept_ref="other_lib.Widget",
                        ),
                    },
                ),
                "Widget": ConceptSpec(
                    the_concept_code="Widget",
                    description="A local widget that should be pruned",
                    refines="Text",
                ),
            },
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result.concept is not None
        assert "Container" in result.concept
        # Widget should be pruned because 'other_lib.Widget' is external
        assert "Widget" not in result.concept

    # --- Tests for pipe lookup masking ---

    def test_prune_warns_missing_pipe(self, caplog: pytest.LogCaptureFixture) -> None:
        """A sequence referencing a non-existent pipe should log a warning and not crash."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="main_sequence",
            pipes={
                "main_sequence": PipeSequenceSpec.model_construct(
                    pipe_code="main_sequence",
                    description="Main",
                    type="PipeSequence",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    steps=[
                        SubPipeSpec(pipe_code="existing_pipe", result="result"),
                        SubPipeSpec(pipe_code="missing_pipe", result="other_result"),
                    ],
                ),
                "existing_pipe": PipeLLMSpec.model_construct(
                    pipe_code="existing_pipe",
                    description="Existing pipe",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    llm_talent="data-retrieval",
                    prompt="Generate text",
                ),
            },
            concepts={},
        )

        with caplog.at_level(logging.WARNING):
            builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert any("missing_pipe" in record.message and "not found" in record.message for record in caplog.records)

    def test_prune_missing_pipe_not_in_reachable(self) -> None:
        """A non-existent pipe referenced by a sequence should not be in reachable_pipes, allowing orphan pipes to be pruned."""
        builder_loop = BuilderLoop()

        bundle = _make_bundle_for_prune(
            domain="my_domain",
            main_pipe="main_sequence",
            pipes={
                "main_sequence": PipeSequenceSpec.model_construct(
                    pipe_code="main_sequence",
                    description="Main",
                    type="PipeSequence",
                    pipe_category="PipeController",
                    inputs={},
                    output="Text",
                    steps=[SubPipeSpec(pipe_code="missing_pipe", result="result")],
                ),
                "orphan_pipe": PipeLLMSpec.model_construct(
                    pipe_code="orphan_pipe",
                    description="Orphan pipe",
                    type="PipeLLM",
                    pipe_category="PipeOperator",
                    inputs={},
                    output="Text",
                    llm_talent="data-retrieval",
                    prompt="Orphan",
                ),
            },
            concepts={},
        )

        result = builder_loop._prune_unreachable_specs(pipelex_bundle_spec=bundle)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # orphan_pipe should be pruned since it's not reachable from main
        assert result.pipe is not None
        assert "orphan_pipe" not in result.pipe
        # main_sequence should remain
        assert "main_sequence" in result.pipe
