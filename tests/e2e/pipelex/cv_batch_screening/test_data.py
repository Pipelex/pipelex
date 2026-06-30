from typing import ClassVar

# The CV batch screening bundle is shared test data: the direct-mode e2e here, the
# Temporal integration suite (in pipelex-temporal), and the /temporal-e2e-validate skill
# all exercise the same .mthds. Each repo keeps its own copy of the crate so neither
# depends on the other's test tree.
_CRATE_DIR: str = "tests/e2e/pipelex/cv_batch_screening/library_crate"


class CvBatchScreeningTemporalTestData:
    """Nested-controller CV batch screening pipeline sourced from pipelex-demos example 21.

    Exercises PipeSequence -> PipeSequence -> PipeBatch -> PipeSequence with PipeExtract +
    PipeLLM operators in both the inner job-offer branch and the per-CV batch branch.
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
