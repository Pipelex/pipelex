"""The `InferenceErrorCategory` -> `ErrorDomain` derivation on the `CogtError` family.

An inference failure used to report no `error_domain` at all, so every one of them — a
content-policy refusal included — answered HTTP 500. The category the worker already
assigned is the authoritative statement of *whose fault it is*, so the domain is derived
from it rather than declared a second time on each of the several dozen leaf classes.
"""

import pytest

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from tests.unit.pipelex.cogt.test_data import ExceptionTestData


class _ExplicitInputDomainError(CogtError):
    """Test-only leaf that declares a domain of its own, against its category's grain."""

    error_domain = ErrorDomain.INPUT
    error_category = InferenceErrorCategory.CONFIGURATION


class _InputDomainCauseError(PipelexError):
    """Test-only non-Cogt cause carrying an INPUT domain, to exercise the cause fallback."""

    error_domain = ErrorDomain.INPUT


class TestInferenceErrorDomain:
    """InferenceErrorCategory.error_domain, and how CogtError.to_error_report() derives from it."""

    # --- the mapping itself ---

    @pytest.mark.parametrize(
        ("_topic", "category", "expected_domain", "_expected_status"),
        ExceptionTestData.CATEGORY_DOMAIN_CASES,
    )
    def test_category_error_domain(
        self,
        _topic: str,
        category: InferenceErrorCategory,
        expected_domain: ErrorDomain | None,
        _expected_status: int,
    ) -> None:
        """Each category maps to the domain that says who can fix that class of failure."""
        assert category.error_domain is expected_domain

    def test_category_domain_cases_cover_every_category(self) -> None:
        """The parametrized table is exhaustive — a new category cannot slip in undecided."""
        covered = {category for _topic, category, _domain, _status in ExceptionTestData.CATEGORY_DOMAIN_CASES}
        assert covered == set(InferenceErrorCategory)

    def test_unknown_asserts_no_domain(self) -> None:
        """UNKNOWN means classification failed, so it must not assert a domain it does not know."""
        assert InferenceErrorCategory.UNKNOWN.error_domain is None

    # --- the derivation on the report ---

    @pytest.mark.parametrize(
        ("_topic", "category", "expected_domain", "expected_status"),
        ExceptionTestData.CATEGORY_DOMAIN_CASES,
    )
    def test_report_derives_domain_from_category(
        self,
        _topic: str,
        category: InferenceErrorCategory,
        expected_domain: ErrorDomain | None,
        expected_status: int,
    ) -> None:
        """A categorized CogtError reports the derived domain and the HTTP status it implies."""
        report = LLMCompletionError("boom", error_category=category).to_error_report()
        assert report.error_domain == expected_domain
        assert report.http_status == expected_status

    def test_content_failure_is_now_a_422(self) -> None:
        """The behavior change: a content-classified inference failure is the caller's to fix."""
        report = LLMCompletionError("the prompt was refused", error_category=InferenceErrorCategory.CONTENT).to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.http_status == 422

    def test_uncategorized_cogt_error_still_has_no_domain(self) -> None:
        """No category means nothing to derive from — the report stays unclassified, and 500."""
        report = CogtError("plain error").to_error_report()
        assert report.error_domain is None
        assert report.http_status == 500

    def test_explicit_class_domain_beats_the_derivation(self) -> None:
        """A leaf that declares its own domain keeps it, even when its category maps elsewhere."""
        report = _ExplicitInputDomainError("declared its own domain").to_error_report()
        assert report.error_category == InferenceErrorCategory.CONFIGURATION
        assert report.error_domain == ErrorDomain.INPUT

    def test_uncategorized_cogt_error_still_inherits_the_cause_domain(self) -> None:
        """With nothing of its own to derive from, the cause chain still supplies the domain."""
        cogt_error = CogtError("wrapped")
        cogt_error.__cause__ = _InputDomainCauseError("the caller's fault")
        report = cogt_error.to_error_report()
        assert report.error_domain == ErrorDomain.INPUT

    def test_own_category_beats_the_cause_domain(self) -> None:
        """Wrapper-wins: the outer error's own category decides, as it already does for the category."""
        cogt_error = CogtError("wrapped", error_category=InferenceErrorCategory.CONFIGURATION)
        cogt_error.__cause__ = _InputDomainCauseError("the caller's fault")
        report = cogt_error.to_error_report()
        assert report.error_domain == ErrorDomain.CONFIG

    def test_provider_429_still_wins_over_the_derived_domain(self) -> None:
        """The rate-limit passthrough is checked before the domain, so CAPACITY -> RUNTIME cannot mask it."""
        report = LLMCompletionError(
            "rate limited",
            error_category=InferenceErrorCategory.CAPACITY,
            provider_metadata=ProviderErrorMetadata(provider=ProviderName.OPENAI, sdk_exception_type="RateLimitError", status_code=429),
        ).to_error_report()
        assert report.error_domain == ErrorDomain.RUNTIME
        assert report.http_status == 429

    # --- the invariant that keeps the two fields from disagreeing on the wire ---

    @pytest.mark.parametrize(
        ("_topic", "category", "_expected_domain", "_expected_status"),
        ExceptionTestData.CATEGORY_DOMAIN_CASES,
    )
    def test_domain_and_category_never_disagree(
        self,
        _topic: str,
        category: InferenceErrorCategory,
        _expected_domain: ErrorDomain | None,
        _expected_status: int,
    ) -> None:
        """For any CogtError with a category and no declared domain, the two report fields agree."""
        report = LLMCompletionError("boom", error_category=category).to_error_report()
        assert report.error_category is not None
        assert report.error_domain == InferenceErrorCategory(report.error_category).error_domain
