from typing import ClassVar

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent


class PipeTestCases:
    SYSTEM_PROMPT = "You are a pirate, you always talk like a pirate."
    USER_PROMPT = "In 3 sentences, tell me about the sea."
    USER_TEXT_TRICKY_1 = """
        When my son was 7 he was 3ft tall. When he was 8 he was 4ft tall. When he was 9 he was 5ft tall.
        How tall do you think he was when he was 12? and at 15?
        """

    # Create simple Stuff objects
    SIMPLE_STUFF = StuffFactory.make_stuff(
        name="text",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
    )

    IMG_EXPENSE_REPORT_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/invoices/invoice_1.png"
    IMG_FASHION_PHOTO_1 = "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/fashion/fashion_photo_1.jpg"
    JOB_OFFER_PDF_LOCAL = "tests/data/documents/Job-Offer.pdf"
    SIMPLE_STUFF_TEXT = StuffFactory.make_stuff(
        name="text",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text="Describe a t-shirt in 2 sentences"),
    )
    SIMPLE_STUFF_IMAGE = StuffFactory.make_stuff(
        name="image",
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
        content=ImageContent(url=IMG_FASHION_PHOTO_1),
    )

    BATCH_TEST: ClassVar[list[tuple[str, Stuff, str, str]]] = [  # pipe_code, stuff, input_list_stuff_name, input_item_stuff_name
        (
            "batch_test",
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                name="colors",
                content=ListContent(
                    items=[
                        TextContent(text="blue"),
                        TextContent(text="red"),
                        TextContent(text="green"),
                    ]
                ),
            ),
            "colors",
            "color",
        ),
    ]
    STUFF_AND_PIPE: ClassVar[list[tuple[str, Stuff, str]]] = [  # topic, stuff, pipe_code
        # TODO: fix testing implict concept
        # (
        #     "Process Simple Text",
        #     SIMPLE_STUFF,
        #     "test_implicit_concept",
        # ),
        # (
        #     "Process Simple Text",
        #     SIMPLE_STUFF_TEXT,
        #     "simple_llm_test_from_text",
        # ),
        (
            "Process Simple Image",
            SIMPLE_STUFF_IMAGE,
            "simple_llm_test_from_image",
        ),
    ]

    NO_INPUT: ClassVar[list[tuple[str, str]]] = [  # topic, pipe
        (
            "Test with no input",
            "test_no_input",
        ),
        (
            "Imagine nature products of different colors",
            "imagine_nature_product_list",
        ),
        (
            "Create characters",
            "create_characters",
        ),
    ]


class LibraryCrateTestData:
    """Test constants for LibraryCrate integration tests.

    Uses a PipeSequence bundle with only native Text concepts (no dynamic classes)
    to avoid the Layer 1 Kajson deserialization issue (Phase 3). This still fully
    tests Layer 2 (pipe resolution via get_required_pipe on the worker).
    """

    BUNDLE_DIR: ClassVar[str] = "tests/integration/pipelex/temporal/library_crate"
    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds"
    PIPE_CODE: ClassVar[str] = "native_text_sequence"
    DOMAIN: ClassVar[str] = "native_text_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "native_text_test.native_text_sequence",
        "native_text_test.step_one",
        "native_text_test.step_two",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "step_one_result",
        "step_two_result",
    ]


class DeferredHydrationTestData:
    """Test constants for Phase 3 deferred hydration integration tests.

    Uses a PipeSequence bundle with a custom concept (Greeting) that has an inline
    structure — this triggers dynamic class generation and exercises the full
    deferred hydration + scoped ClassRegistry path.
    """

    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds"
    PIPE_CODE: ClassVar[str] = "dynamic_greeting_sequence"
    DOMAIN: ClassVar[str] = "dynamic_concept_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "dynamic_concept_test.dynamic_greeting_sequence",
        "dynamic_concept_test.generate_greeting",
        "dynamic_concept_test.summarize_greeting",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "greeting_result",
        "summary_result",
    ]


_CRATE_DIR: str = "tests/integration/pipelex/temporal/library_crate"


class ConflictConceptAlphaTestData:
    """Concept 'Result' with score (integer) + label (text).

    Paired with ConflictConceptBetaTestData which defines a different 'Result'.
    Tests that per-workflow ClassRegistry scoping keeps them isolated.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/conflict_concept_alpha.mthds"
    PIPE_CODE: ClassVar[str] = "alpha_pipeline"
    DOMAIN: ClassVar[str] = "conflict_alpha"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "conflict_alpha.alpha_pipeline",
        "conflict_alpha.alpha_generate",
        "conflict_alpha.alpha_summarize",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "alpha_result",
        "alpha_summary",
    ]

    EXPECTED_RESULT_FIELDS: ClassVar[list[str]] = ["score", "label"]


class ConflictConceptBetaTestData:
    """Concept 'Result' with value (text) + confidence (number) + is_valid (text).

    Paired with ConflictConceptAlphaTestData which defines a different 'Result'.
    Tests that per-workflow ClassRegistry scoping keeps them isolated.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/conflict_concept_beta.mthds"
    PIPE_CODE: ClassVar[str] = "beta_pipeline"
    DOMAIN: ClassVar[str] = "conflict_beta"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "conflict_beta.beta_pipeline",
        "conflict_beta.beta_generate",
        "conflict_beta.beta_summarize",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "beta_result",
        "beta_summary",
    ]

    EXPECTED_RESULT_FIELDS: ClassVar[list[str]] = ["value", "confidence", "is_valid"]


class ConflictPipeAlphaTestData:
    """Pipe 'alpha_shared_step' as PipeLLM about colors.

    Paired with ConflictPipeBetaTestData. Tests that per-workflow library scoping
    via ContextVar resolves the correct pipe_ref for each workflow.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/conflict_pipe_alpha.mthds"
    PIPE_CODE: ClassVar[str] = "pipe_alpha_pipeline"
    DOMAIN: ClassVar[str] = "pipe_conflict_alpha"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "pipe_conflict_alpha.pipe_alpha_pipeline",
        "pipe_conflict_alpha.alpha_shared_step",
        "pipe_conflict_alpha.alpha_finalize",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "step_result",
        "final_result",
    ]


class ConflictPipeBetaTestData:
    """Pipe 'beta_shared_step' as PipeLLM about animals.

    Paired with ConflictPipeAlphaTestData. Tests that per-workflow library scoping
    via ContextVar resolves the correct pipe_ref for each workflow.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/conflict_pipe_beta.mthds"
    PIPE_CODE: ClassVar[str] = "pipe_beta_pipeline"
    DOMAIN: ClassVar[str] = "pipe_conflict_beta"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "pipe_conflict_beta.pipe_beta_pipeline",
        "pipe_conflict_beta.beta_shared_step",
        "pipe_conflict_beta.beta_finalize",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "step_result",
        "final_result",
    ]


class MultiConceptAlphaTestData:
    """Profile(name, age) + Summary(headline, body).

    Paired with MultiConceptBetaTestData which defines different Profile and Summary.
    Tests worst-case: multiple same-named dynamic classes across concurrent workflows.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/multi_concept_alpha.mthds"
    PIPE_CODE: ClassVar[str] = "multi_alpha_pipeline"
    DOMAIN: ClassVar[str] = "multi_alpha"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "multi_alpha.multi_alpha_pipeline",
        "multi_alpha.multi_alpha_generate_profile",
        "multi_alpha.multi_alpha_generate_summary",
        "multi_alpha.multi_alpha_finalize",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "profile_result",
        "summary_result",
        "final_result",
    ]

    EXPECTED_PROFILE_FIELDS: ClassVar[list[str]] = ["name", "age"]
    EXPECTED_SUMMARY_FIELDS: ClassVar[list[str]] = ["headline", "body"]


class MultiConceptBetaTestData:
    """Profile(title, department, level) + Summary(content).

    Paired with MultiConceptAlphaTestData which defines different Profile and Summary.
    Tests worst-case: multiple same-named dynamic classes across concurrent workflows.
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/multi_concept_beta.mthds"
    PIPE_CODE: ClassVar[str] = "multi_beta_pipeline"
    DOMAIN: ClassVar[str] = "multi_beta"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "multi_beta.multi_beta_pipeline",
        "multi_beta.multi_beta_generate_profile",
        "multi_beta.multi_beta_generate_summary",
        "multi_beta.multi_beta_finalize",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "profile_result",
        "summary_result",
        "final_result",
    ]

    EXPECTED_PROFILE_FIELDS: ClassVar[list[str]] = ["title", "department", "level"]
    EXPECTED_SUMMARY_FIELDS: ClassVar[list[str]] = ["content"]


class PipeConditionTemporalTestData:
    """PipeCondition within a PipeSequence for Temporal child workflow dispatch testing."""

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_condition.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_condition_sequence"
    DOMAIN: ClassVar[str] = "temporal_condition_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "temporal_condition_test.temporal_condition_sequence",
        "temporal_condition_test.generate_category",
        "temporal_condition_test.route_by_category",
        "temporal_condition_test.handle_alpha",
        "temporal_condition_test.handle_beta",
        "temporal_condition_test.handle_default",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "category_text",
        "routed_result",
    ]


class PipeParallelTemporalTestData:
    """PipeParallel within a PipeSequence for Temporal concurrent child workflow dispatch testing."""

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_parallel.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_parallel_sequence"
    DOMAIN: ClassVar[str] = "temporal_parallel_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "temporal_parallel_test.temporal_parallel_sequence",
        "temporal_parallel_test.analyze_in_parallel",
        "temporal_parallel_test.branch_tone",
        "temporal_parallel_test.branch_length",
        "temporal_parallel_test.summarize_results",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "tone_result",
        "length_result",
        "summary",
    ]


class PipeBatchTemporalTestData:
    """PipeBatch within a PipeSequence for Temporal fan-out child workflow dispatch testing."""

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_batch.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_batch_sequence"
    DOMAIN: ClassVar[str] = "temporal_batch_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "temporal_batch_test.temporal_batch_sequence",
        "temporal_batch_test.temporal_generate_topics",
        "temporal_batch_test.batch_temporal_describe_topics",
        "temporal_batch_test.temporal_describe_topic",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "topics",
        "notes",
    ]


class PipeComposeTemporalTestData:
    """PipeCompose operator within a PipeSequence with deferred hydration of Report concept."""

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_compose.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_compose_sequence"
    DOMAIN: ClassVar[str] = "temporal_compose_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "temporal_compose_test.temporal_compose_sequence",
        "temporal_compose_test.generate_title",
        "temporal_compose_test.generate_body",
        "temporal_compose_test.compose_report",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "title_text",
        "body_text",
        "final_report",
    ]

    EXPECTED_REPORT_FIELDS: ClassVar[list[str]] = ["title", "body"]


class CombinedPipelineTemporalTestData:
    """Combined PipeParallel + PipeCondition in a PipeSequence for nested Temporal dispatch testing."""

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/temporal_combined.mthds"
    PIPE_CODE: ClassVar[str] = "temporal_combined_pipeline"
    DOMAIN: ClassVar[str] = "temporal_combined_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "temporal_combined_test.temporal_combined_pipeline",
        "temporal_combined_test.parallel_generate",
        "temporal_combined_test.generate_part_a",
        "temporal_combined_test.generate_part_b",
        "temporal_combined_test.quality_gate",
        "temporal_combined_test.handle_failure",
        "temporal_combined_test.produce_report",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "part_a",
        "part_b",
        "final_report",
    ]

    EXPECTED_REPORT_FIELDS: ClassVar[list[str]] = ["assessment", "confidence"]


class PayloadCodecPipelineTestData:
    """Test constants for StoragePayloadCodec integration tests with real pipe execution.

    Reuses existing bundles to prove the codec is transparent — same pipelines
    work unchanged when payloads are offloaded to storage.
    """

    # Reuse native_text_sequence for single/multi-step codec tests
    NATIVE_BUNDLE_FILE: ClassVar[str] = LibraryCrateTestData.BUNDLE_FILE
    NATIVE_PIPE_CODE: ClassVar[str] = LibraryCrateTestData.PIPE_CODE
    NATIVE_EXPECTED_STUFF_NAMES: ClassVar[list[str]] = LibraryCrateTestData.EXPECTED_STUFF_NAMES

    # Reuse dynamic_concept_sequence for dynamic concept + codec test
    DYNAMIC_BUNDLE_FILE: ClassVar[str] = DeferredHydrationTestData.BUNDLE_FILE
    DYNAMIC_PIPE_CODE: ClassVar[str] = DeferredHydrationTestData.PIPE_CODE
    DYNAMIC_EXPECTED_STUFF_NAMES: ClassVar[list[str]] = DeferredHydrationTestData.EXPECTED_STUFF_NAMES

    # Codec config
    SIZE_THRESHOLD: ClassVar[int] = 1024
    STORAGE_PREFIX: ClassVar[str] = "test-codec-pipeline/"


class LargePayloadTestData:
    """Test constants for large payload stress testing through Temporal with codec."""

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/large_payload_sequence.mthds"
    PIPE_CODE: ClassVar[str] = "large_payload_sequence"
    DOMAIN: ClassVar[str] = "large_payload_test"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "large_payload_test.large_payload_sequence",
        "large_payload_test.verbose_step_one",
        "large_payload_test.verbose_step_two",
        "large_payload_test.verbose_step_three",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "step_one_result",
        "step_two_result",
        "step_three_result",
    ]

    SIZE_THRESHOLD: ClassVar[int] = 1024
    STORAGE_PREFIX: ClassVar[str] = "test-large-payload/"


class CvBatchScreeningTemporalTestData:
    """Nested-controller CV batch screening pipeline sourced from pipelex-demos example 21.

    Exercises PipeSequence -> PipeSequence -> PipeBatch -> PipeSequence with PipeExtract +
    PipeLLM operators in both the inner job-offer branch and the per-CV batch branch.
    Used by the e2e suite (direct mode), the temporal integration suite (in-process
    server + worker), and the `/temporal-e2e-validate` skill (distributed 3-process).
    """

    BUNDLE_FILE: ClassVar[str] = f"{_CRATE_DIR}/cv_batch_screening.mthds"
    INPUTS_FILE: ClassVar[str] = f"{_CRATE_DIR}/cv_batch_screening_inputs.json"
    PIPE_CODE: ClassVar[str] = "batch_analyze_cvs_for_job_offer"
    DOMAIN: ClassVar[str] = "cv_batch_screening"

    EXPECTED_PIPE_REFS: ClassVar[list[str]] = [
        "cv_batch_screening.batch_analyze_cvs_for_job_offer",
        "cv_batch_screening.prepare_job_offer",
        "cv_batch_screening.extract_one_job_offer",
        "cv_batch_screening.analyze_job_requirements",
        "cv_batch_screening.process_cv",
        "cv_batch_screening.extract_one_cv",
        "cv_batch_screening.analyze_one_cv",
        "cv_batch_screening.analyze_match",
    ]

    EXPECTED_STUFF_NAMES: ClassVar[list[str]] = [
        "job_requirements",
        "match_analyses",
    ]

    EXPECTED_CANDIDATE_MATCH_FIELDS: ClassVar[list[str]] = [
        "match_score",
        "strengths",
        "gaps",
        "overall_assessment",
    ]


class PipeOcrTestCases:
    PIPE_OCR_IMAGE_TEST_CASES: ClassVar[list[str]] = [
        # LOCAL
        "tests/data/documents/solar_system.png",
        # REMOTE
        "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.png",
    ]
    PIPE_OCR_PDF_TEST_CASES: ClassVar[list[str]] = [
        # LOCAL
        "tests/data/documents/solar_system.pdf",
        # REMOTE
        "https://storage.googleapis.com/public_test_files_7fa6_4277_9ab/documents/solar_system.pdf",
    ]
