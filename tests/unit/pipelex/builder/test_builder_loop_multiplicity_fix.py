from pipelex.builder.builder_loop import BuilderLoop
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec

ERROR_MESSAGE_TEMPLATE = (
    "Dry run failed for pipe '{parent_pipe}': In pipe '{compose_pipe}' (output: {output_concept}): "
    "Cannot validate {output_concept}: Validation error(s):\n"
    "Other validation errors:\n"
    "{field_name}: string_type: Input should be a valid string\n"
    "Field type summary:\n"
    "  {field_name}: ListContent (expected str) <-- MISMATCH"
)

ERROR_MESSAGE_MULTI_MISMATCH_TEMPLATE = (
    "Dry run failed for pipe 'main_sequence': In pipe 'compose_result' (output: ResultPackage): "
    "Cannot validate ResultPackage: Validation error(s):\n"
    "Other validation errors:\n"
    "questions: string_type: Input should be a valid string\n"
    "answers: string_type: Input should be a valid string\n"
    "Field type summary:\n"
    "  title: str (expected str)\n"
    "  questions: ListContent (expected str) <-- MISMATCH\n"
    "  answers: ListContent (expected str) <-- MISMATCH"
)


def _make_bundle_with_compose(
    compose_pipe_code: str = "compose_result",
    output_concept_code: str = "ResultPackage",
    field_name: str = "interview_questions",
    input_variable: str = "interview_questions",
    input_concept: str = "InterviewQuestion",
    field_type: ConceptStructureSpecFieldType = ConceptStructureSpecFieldType.TEXT,
    item_type: str | None = None,
    item_concept_ref: str | None = None,
) -> PipelexBundleSpec:
    """Create a minimal PipelexBundleSpec with a PipeCompose for testing."""
    return PipelexBundleSpec(
        domain="test",
        main_pipe=compose_pipe_code,
        concept={
            "InterviewQuestion": ConceptSpec(
                the_concept_code="InterviewQuestion",
                description="An interview question",
                refines="Text",
            ),
            output_concept_code: ConceptSpec(
                the_concept_code=output_concept_code,
                description="A result package",
                structure={
                    "title": ConceptStructureSpec(
                        the_field_name="title",
                        description="A title",
                        type=ConceptStructureSpecFieldType.TEXT,
                    ),
                    field_name: ConceptStructureSpec(
                        the_field_name=field_name,
                        description="Some items",
                        type=field_type,
                        item_type=item_type,
                        item_concept_ref=item_concept_ref,
                    ),
                },
            ),
        },
        pipe={
            compose_pipe_code: PipeComposeSpec(
                pipe_code=compose_pipe_code,
                description="Compose the result",
                inputs={
                    "title": "Text",
                    input_variable: input_concept,
                },
                output=output_concept_code,
                construct_spec={
                    "title": {"from": "title"},
                    field_name: {"from": input_variable},
                },
            ),
        },
    )


class TestBuilderLoopMultiplicityFix:
    """Tests for _fix_dry_run_compose_multiplicity_mismatch in BuilderLoop."""

    def test_fix_list_content_to_str_mismatch(self):
        """Fix ListContent vs str mismatch: adds [] to input and changes concept field to list."""
        bundle_spec = _make_bundle_with_compose(
            compose_pipe_code="compose_preparation_package",
            output_concept_code="InterviewPreparationPackage",
            field_name="interview_questions",
            input_variable="interview_questions",
            input_concept="InterviewQuestion",
        )

        error_message = ERROR_MESSAGE_TEMPLATE.format(
            parent_pipe="prepare_interview",
            compose_pipe="compose_preparation_package",
            output_concept="InterviewPreparationPackage",
            field_name="interview_questions",
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        # Check a pipe was fixed
        assert len(fixed_pipes) == 1

        # Check the pipe input was updated to add []
        assert bundle_spec.pipe is not None
        pipe_spec = bundle_spec.pipe["compose_preparation_package"]
        assert isinstance(pipe_spec, PipeComposeSpec)
        assert pipe_spec.inputs is not None
        assert pipe_spec.inputs["interview_questions"] == "InterviewQuestion[]"

        # Check the concept structure field was updated to LIST
        assert bundle_spec.concept is not None
        concept_spec = bundle_spec.concept["InterviewPreparationPackage"]
        assert isinstance(concept_spec, ConceptSpec)
        assert concept_spec.structure is not None
        field_spec = concept_spec.structure["interview_questions"]
        assert field_spec.type == ConceptStructureSpecFieldType.LIST
        assert field_spec.item_type == "concept"
        assert field_spec.item_concept_ref == "InterviewQuestion"

    def test_fix_multiple_mismatches(self):
        """Fix multiple mismatched fields in one error."""
        bundle_spec = PipelexBundleSpec(
            domain="test",
            main_pipe="compose_result",
            concept={
                "Question": ConceptSpec(
                    the_concept_code="Question",
                    description="A question",
                    refines="Text",
                ),
                "Answer": ConceptSpec(
                    the_concept_code="Answer",
                    description="An answer",
                    refines="Text",
                ),
                "ResultPackage": ConceptSpec(
                    the_concept_code="ResultPackage",
                    description="A result package",
                    structure={
                        "title": ConceptStructureSpec(
                            the_field_name="title",
                            description="A title",
                            type=ConceptStructureSpecFieldType.TEXT,
                        ),
                        "questions": ConceptStructureSpec(
                            the_field_name="questions",
                            description="List of questions",
                            type=ConceptStructureSpecFieldType.TEXT,
                        ),
                        "answers": ConceptStructureSpec(
                            the_field_name="answers",
                            description="List of answers",
                            type=ConceptStructureSpecFieldType.TEXT,
                        ),
                    },
                ),
            },
            pipe={
                "compose_result": PipeComposeSpec(
                    pipe_code="compose_result",
                    description="Compose result",
                    inputs={
                        "title": "Text",
                        "questions": "Question",
                        "answers": "Answer",
                    },
                    output="ResultPackage",
                    construct_spec={
                        "title": {"from": "title"},
                        "questions": {"from": "questions"},
                        "answers": {"from": "answers"},
                    },
                ),
            },
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=ERROR_MESSAGE_MULTI_MISMATCH_TEMPLATE,
            pipelex_bundle_spec=bundle_spec,
        )

        assert len(fixed_pipes) == 1

        # Check both inputs were fixed
        assert bundle_spec.pipe is not None
        pipe_spec = bundle_spec.pipe["compose_result"]
        assert isinstance(pipe_spec, PipeComposeSpec)
        assert pipe_spec.inputs is not None
        assert pipe_spec.inputs["questions"] == "Question[]"
        assert pipe_spec.inputs["answers"] == "Answer[]"
        # Title should remain unchanged
        assert pipe_spec.inputs["title"] == "Text"

        # Check both concept structure fields were fixed
        assert bundle_spec.concept is not None
        concept_spec = bundle_spec.concept["ResultPackage"]
        assert isinstance(concept_spec, ConceptSpec)
        assert concept_spec.structure is not None
        assert concept_spec.structure["questions"].type == ConceptStructureSpecFieldType.LIST
        assert concept_spec.structure["questions"].item_concept_ref == "Question"
        assert concept_spec.structure["answers"].type == ConceptStructureSpecFieldType.LIST
        assert concept_spec.structure["answers"].item_concept_ref == "Answer"
        # Title field should remain TEXT
        assert concept_spec.structure["title"].type == ConceptStructureSpecFieldType.TEXT

    def test_skip_input_already_has_multiplicity(self):
        """Skip fixing when the input already has multiplicity notation."""
        bundle_spec = _make_bundle_with_compose(
            compose_pipe_code="compose_preparation_package",
            output_concept_code="InterviewPreparationPackage",
            field_name="interview_questions",
            input_variable="interview_questions",
            input_concept="InterviewQuestion[]",
            field_type=ConceptStructureSpecFieldType.LIST,
            item_type="concept",
            item_concept_ref="InterviewQuestion",
        )

        error_message = ERROR_MESSAGE_TEMPLATE.format(
            parent_pipe="prepare_interview",
            compose_pipe="compose_preparation_package",
            output_concept="InterviewPreparationPackage",
            field_name="interview_questions",
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        # No pipes should be fixed since input already has multiplicity
        assert len(fixed_pipes) == 0

    def test_fix_concept_field_when_input_already_has_multiplicity(self):
        """Fix concept field even when the input already has multiplicity notation (e.g., InterviewQuestion[5])."""
        bundle_spec = _make_bundle_with_compose(
            compose_pipe_code="compose_final_report",
            output_concept_code="InterviewPreparationReport",
            field_name="interview_questions",
            input_variable="interview_questions",
            input_concept="InterviewQuestion[5]",
            field_type=ConceptStructureSpecFieldType.TEXT,
        )

        error_message = ERROR_MESSAGE_TEMPLATE.format(
            parent_pipe="prepare_interview",
            compose_pipe="compose_final_report",
            output_concept="InterviewPreparationReport",
            field_name="interview_questions",
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        # Pipe should be fixed (concept field changed)
        assert len(fixed_pipes) == 1

        # Input should remain unchanged (already had multiplicity)
        assert bundle_spec.pipe is not None
        pipe_spec = bundle_spec.pipe["compose_final_report"]
        assert isinstance(pipe_spec, PipeComposeSpec)
        assert pipe_spec.inputs is not None
        assert pipe_spec.inputs["interview_questions"] == "InterviewQuestion[5]"

        # Concept structure field should be updated to LIST
        assert bundle_spec.concept is not None
        concept_spec = bundle_spec.concept["InterviewPreparationReport"]
        assert isinstance(concept_spec, ConceptSpec)
        assert concept_spec.structure is not None
        field_spec = concept_spec.structure["interview_questions"]
        assert field_spec.type == ConceptStructureSpecFieldType.LIST
        assert field_spec.item_type == "concept"
        assert field_spec.item_concept_ref == "InterviewQuestion"

    def test_skip_non_pipe_compose(self):
        """Skip fixing when the pipe is not a PipeComposeSpec."""
        bundle_spec = PipelexBundleSpec(
            domain="test",
            main_pipe="some_llm_pipe",
            concept={},
            pipe={
                "some_llm_pipe": PipeLLMSpec(
                    pipe_code="some_llm_pipe",
                    description="An LLM pipe",
                    inputs={"input_text": "Text"},
                    output="Text",
                    model="$retrieval",
                    prompt="Do something with @input_text",
                ),
            },
        )

        error_message = (
            "Dry run failed for pipe 'main': In pipe 'some_llm_pipe' (output: Text): "
            "Cannot validate Text: Validation error(s):\n"
            "Field type summary:\n"
            "  content: ListContent (expected str) <-- MISMATCH"
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        assert len(fixed_pipes) == 0

    def test_skip_no_mismatch_pattern(self):
        """Skip fixing when the error message has no MISMATCH pattern."""
        bundle_spec = _make_bundle_with_compose()

        error_message = "Some other dry run error without mismatch pattern"

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        assert len(fixed_pipes) == 0

    def test_skip_concept_not_in_bundle(self):
        """Fix input but gracefully handle missing concept in bundle."""
        bundle_spec = PipelexBundleSpec(
            domain="test",
            main_pipe="compose_result",
            concept={
                "InterviewQuestion": ConceptSpec(
                    the_concept_code="InterviewQuestion",
                    description="An interview question",
                    refines="Text",
                ),
                # Note: MissingConcept is NOT in the bundle concepts
            },
            pipe={
                "compose_result": PipeComposeSpec(
                    pipe_code="compose_result",
                    description="Compose result",
                    inputs={"questions": "InterviewQuestion"},
                    output="MissingConcept",
                    construct_spec={"questions": {"from": "questions"}},
                ),
            },
        )

        error_message = (
            "Dry run failed for pipe 'main': In pipe 'compose_result' (output: MissingConcept): "
            "Cannot validate MissingConcept: Validation error(s):\n"
            "Field type summary:\n"
            "  questions: ListContent (expected str) <-- MISMATCH"
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        # Pipe input is still fixed even if concept structure can't be updated
        assert len(fixed_pipes) == 1
        assert bundle_spec.pipe is not None
        pipe_spec = bundle_spec.pipe["compose_result"]
        assert isinstance(pipe_spec, PipeComposeSpec)
        assert pipe_spec.inputs is not None
        assert pipe_spec.inputs["questions"] == "InterviewQuestion[]"

    def test_no_pipes_in_bundle(self):
        """Handle empty pipe dict gracefully."""
        # Use model_construct to bypass validation (PipelexBundleSpec requires main_pipe in pipes)
        bundle_spec = PipelexBundleSpec.model_construct(
            domain="test",
            main_pipe="main",
            concept={},
            pipe={},
        )

        error_message = ERROR_MESSAGE_TEMPLATE.format(
            parent_pipe="main",
            compose_pipe="compose_result",
            output_concept="Result",
            field_name="items",
        )

        builder_loop = BuilderLoop()
        fixed_pipes = builder_loop._fix_dry_run_compose_multiplicity_mismatch(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            dry_run_error_message=error_message,
            pipelex_bundle_spec=bundle_spec,
        )

        assert len(fixed_pipes) == 0
