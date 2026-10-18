from collections.abc import Callable

import pytest
import tenacity
from instructor import openai_schema
from instructor.core import InstructorRetryException
from pydantic import BaseModel, ValidationError

from pipelex.cogt.content_generation.llm_generate import make_object_list_schema
from pipelex.cogt.inference.error_classification import (
    ProviderErrorMetadata,
    describe_instructor_failure,
    extract_anthropic_metadata,
    extract_google_metadata,
    extract_mistral_metadata,
    extract_openai_metadata,
    extract_underlying_sdk_exception,
)

# A value no secret pattern matches, standing for the model's answer, which no message carries.
_ANSWER = "confidential-patient-diagnosis"


class _Tally(BaseModel):
    count: int


class _SdkError(Exception):
    """An error a provider's SDK raises as its own, whose text is the provider's."""


def _validation_error_quoting_the_answer(*, schema: type[BaseModel], answer: object) -> ValidationError:
    """The error instructor's own validation raises on the model's answer: it validates with a subclass of the schema."""
    try:
        openai_schema(schema).model_validate(answer)
    except ValidationError as exc:
        return exc
    msg = "The answer was expected to be refused"
    raise AssertionError(msg)


def _retry_error_whose_last_attempt_returned() -> tenacity.RetryError:
    last_attempt = tenacity.Future(attempt_number=2)
    last_attempt.set_result(_Tally(count=1))
    return tenacity.RetryError(last_attempt=last_attempt)


def _retry_error_whose_last_attempt_raised(*, exc: BaseException) -> tenacity.RetryError:
    last_attempt = tenacity.Future(attempt_number=2)
    last_attempt.set_exception(exc)
    return tenacity.RetryError(last_attempt=last_attempt)


def _wrapped(*, cause: BaseException | None) -> InstructorRetryException:
    """An `InstructorRetryException` as instructor raises it: its own text is the last exception's, the answer included."""
    wrapper = InstructorRetryException(
        f"1 validation error for _Tally: count, input_value='{_ANSWER}'",
        last_completion=None,
        n_attempts=2,
        total_usage=0,
        create_kwargs={},
        failed_attempts=[],
    )
    wrapper.__cause__ = cause
    return wrapper


_EXTRACTORS: list[Callable[..., ProviderErrorMetadata]] = [
    extract_openai_metadata,
    extract_anthropic_metadata,
    extract_google_metadata,
    extract_mistral_metadata,
]


class TestDescribeInstructorFailure:
    @pytest.mark.parametrize(
        ("topic", "cause", "expected"),
        [
            ("a retry error whose last attempt raised nothing", _retry_error_whose_last_attempt_returned(), "RetryError"),
            ("no cause at all", None, "InstructorRetryException"),
            ("a cause with a text of its own", ValueError(f"the model said {_ANSWER}"), "ValueError"),
        ],
    )
    def test_an_unrecovered_failure_is_named_by_its_class_alone(self, topic: str, cause: BaseException | None, expected: str) -> None:
        """Nothing was recovered: the wrapper's cause, or the wrapper, is named by its class, never by a text or a repr."""
        reason = describe_instructor_failure(instructor_exc=_wrapped(cause=cause))

        assert reason == expected, topic
        assert "0x" not in reason, topic
        assert _ANSWER not in reason, topic

    def test_a_retry_error_with_nothing_raised_recovers_nothing(self) -> None:
        """The case `describe_instructor_failure` serves: the extraction gives `None`, and the retry error's repr stays out."""
        instructor_exc = _wrapped(cause=_retry_error_whose_last_attempt_returned())

        assert extract_underlying_sdk_exception(instructor_exc) is None
        assert describe_instructor_failure(instructor_exc=instructor_exc) == "RetryError"

    @pytest.mark.parametrize("extract_metadata", _EXTRACTORS)
    def test_the_common_path_locates_the_refusal_by_the_requested_schema(self, extract_metadata: Callable[..., ProviderErrorMetadata]) -> None:
        """Re-asks exhausted on a refused answer: the recovered error is located by the schema, its answer never quoted."""
        refusal = _validation_error_quoting_the_answer(schema=_Tally, answer={"count": _ANSWER})
        underlying = extract_underlying_sdk_exception(_wrapped(cause=_retry_error_whose_last_attempt_raised(exc=refusal)))
        assert underlying is refusal

        metadata = extract_metadata(underlying, validated_type=_Tally)

        assert metadata.message.startswith("count: Input should be a valid integer")
        assert _ANSWER not in metadata.message

    def test_a_list_of_objects_is_located_through_its_wrapper(self) -> None:
        """The wrapper a list of objects is generated as carries its name as its title, so its refusal is located too."""
        list_schema = make_object_list_schema(item_class=_Tally, item_class_name="Tally")
        refusal = _validation_error_quoting_the_answer(schema=list_schema, answer={"items": [{"count": 1}, {"count": _ANSWER}]})

        metadata = extract_openai_metadata(refusal, validated_type=list_schema)

        assert metadata.message.startswith("items.1.count: Input should be a valid integer")
        assert _ANSWER not in metadata.message

    @pytest.mark.parametrize("extract_metadata", _EXTRACTORS)
    def test_any_other_parsing_failure_is_named_by_its_class_alone(self, extract_metadata: Callable[..., ProviderErrorMetadata]) -> None:
        """Instructor's OpenAI parser asserts on a refusal with the model's answer in its text: the recovered assertion is named by its class."""
        refusal = AssertionError(f"Unable to generate a response due to {_ANSWER}")
        underlying = extract_underlying_sdk_exception(_wrapped(cause=refusal))
        assert underlying is refusal

        metadata = extract_metadata(underlying, validated_type=_Tally, sdk_error_types=(_SdkError,))

        assert metadata.message == "AssertionError"
        assert metadata.sdk_exception_type == "AssertionError"

    @pytest.mark.parametrize("extract_metadata", _EXTRACTORS)
    def test_a_recovered_sdk_error_keeps_the_provider_s_text(self, extract_metadata: Callable[..., ProviderErrorMetadata]) -> None:
        """A call that failed in transport ends the loop on the SDK's own error, whose text the classification reads."""
        sdk_error = _SdkError("You exceeded your current quota")
        underlying = extract_underlying_sdk_exception(_wrapped(cause=sdk_error))

        metadata = extract_metadata(underlying, validated_type=_Tally, sdk_error_types=(_SdkError,))

        assert metadata.message == "You exceeded your current quota"
