from datetime import datetime

from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.search.search_report import SearchTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata, UnitJobId
from pipelex.reporting.reporting_types import AnyTokensUsage

RATED_NB_TOKENS: NbTokensByCategoryDict = {
    TokenCategory.INPUT: 1000,
    TokenCategory.INPUT_CACHED: 400,
    TokenCategory.OUTPUT: 250,
}
RATED_UNIT_COSTS: CostsByCategoryDict = {
    CostCategory.INPUT: 2.5,
    CostCategory.INPUT_CACHED: 1.25,
    CostCategory.OUTPUT: 10.0,
}
# (600 non-cached × $2.5/M) + (400 cached × $1.25/M) + (250 output × $10/M), written in the
# exact per-token arithmetic the cost engine performs so equality asserts hold bit-for-bit.
RATED_EXPECTED_COST = 600 * (2.5 / 1_000_000) + 400 * (1.25 / 1_000_000) + 250 * (10.0 / 1_000_000)


class UsageFixtures:
    """Shared usage fixtures for the wire-record and cost tests.

    The cost-parity test and the wire-record tests read the SAME records, pinning the wire
    ``cost`` to the ``CostRegistry`` totals so the two presentations of the one cost engine
    cannot drift apart.
    """

    @staticmethod
    def full_job_metadata(*, unit_job_id: UnitJobId, job_category: JobCategory) -> JobMetadata:
        """A JobMetadata with EVERY optional field populated, so leak tests prove the trim."""
        return JobMetadata(
            user_id="user-42",
            pipeline_run_id="plr-fixture",
            pipe_code="analyze_contract",
            session_id="session-abc",
            request_id="req-123",
            pipe_run_id="a1b2c3d4e5f60718",
            content_generation_job_id="cgj-9",
            unit_job_id=unit_job_id,
            job_category=job_category,
            started_at=datetime(2026, 7, 19, 10, 0, 0),
            completed_at=datetime(2026, 7, 19, 10, 0, 5),
        )

    @classmethod
    def llm_usage(cls) -> LLMTokensUsage:
        return LLMTokensUsage(
            job_metadata=cls.full_job_metadata(unit_job_id=UnitJobId.LLM_GEN_TEXT, job_category=JobCategory.LLM_JOB),
            inference_model_name="gpt-4o",
            inference_model_id="gpt-4o-2024-11-20",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        )

    @classmethod
    def img_gen_usage(cls) -> ImgGenTokensUsage:
        return ImgGenTokensUsage(
            job_metadata=cls.full_job_metadata(unit_job_id=UnitJobId.IMG_GEN_TEXT_TO_IMAGE, job_category=JobCategory.IMG_GEN_JOB),
            inference_model_name="gpt-image-1",
            inference_model_id="gpt-image-1-2025",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        )

    @classmethod
    def extract_usage(cls) -> ExtractTokensUsage:
        return ExtractTokensUsage(
            job_metadata=cls.full_job_metadata(unit_job_id=UnitJobId.EXTRACT_PAGES, job_category=JobCategory.EXTRACT_JOB),
            inference_model_name="mistral-ocr",
            inference_model_id="mistral-ocr-2505",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        )

    @classmethod
    def search_usage(cls) -> SearchTokensUsage:
        return SearchTokensUsage(
            job_metadata=cls.full_job_metadata(unit_job_id=UnitJobId.SEARCH_SOURCED_ANSWER, job_category=JobCategory.SEARCH_JOB),
            inference_model_name="sonar-pro",
            inference_model_id="sonar-pro-2025",
            nb_tokens_by_category=dict(RATED_NB_TOKENS),
            unit_costs=dict(RATED_UNIT_COSTS),
        )

    @classmethod
    def all_variants(cls) -> list[AnyTokensUsage]:
        return [cls.llm_usage(), cls.img_gen_usage(), cls.extract_usage(), cls.search_usage()]

    @classmethod
    def unrated_usage(cls) -> LLMTokensUsage:
        """A usage with no rate table (own-GPU model, dry/mock run): wire ``cost`` must be None."""
        usage = cls.llm_usage()
        usage.unit_costs = {}
        return usage

    @classmethod
    def cached_fallback_usage(cls) -> LLMTokensUsage:
        """A usage with cached tokens but no explicit cached rate: the 50%-of-input fallback applies."""
        usage = cls.llm_usage()
        usage.unit_costs = {CostCategory.INPUT: 2.0, CostCategory.OUTPUT: 10.0}
        return usage
