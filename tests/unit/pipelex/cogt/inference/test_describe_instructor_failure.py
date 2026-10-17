import pytest
import tenacity
from instructor.core import InstructorRetryException
from pydantic import BaseModel, ValidationError

from pipelex.cogt.inference.error_classification import describe_instructor_failure

# A value no secret pattern matches, standing for the model's answer, which no message carries.
_ANSWER = "confidential-patient-diagnosis"


class _Tally(BaseModel):
    count: int


def _validation_error_quoting_the_answer() -> ValidationError:
    try:
        _Tally.model_validate({"count": _ANSWER})
    except ValidationError as exc:
        return exc
    msg = "The answer was expected to be refused"
    raise AssertionError(msg)


def _retry_error_whose_last_attempt_returned() -> tenacity.RetryError:
    last_attempt = tenacity.Future(attempt_number=2)
    last_attempt.set_result(_Tally(count=1))
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


class TestDescribeInstructorFailure:
    @pytest.mark.parametrize(
        ("topic", "cause", "validated_type", "expected_start"),
        [
            ("a parse failure, its answer refused", _validation_error_quoting_the_answer(), _Tally, "ValidationError: count: Input should be"),
            ("a parse failure whose schema is not given", _validation_error_quoting_the_answer(), None, "ValidationError: Input should be"),
            ("a failure that is not a parse failure", ValueError("Instructor does not support multiple tool calls"), None, "ValueError: "),
            ("a retry error whose last attempt raised nothing", _retry_error_whose_last_attempt_returned(), None, "RetryError: RetryError["),
            ("no cause at all", None, None, "InstructorRetryException"),
        ],
    )
    def test_the_reason_survives_without_the_model_s_answer(
        self, topic: str, cause: BaseException | None, validated_type: type[BaseModel] | None, expected_start: str
    ) -> None:
        """The reason is the class and the input-free text of what ended the loop, never instructor's own text."""
        reason = describe_instructor_failure(instructor_exc=_wrapped(cause=cause), validated_type=validated_type)

        assert reason.startswith(expected_start), topic
        assert _ANSWER not in reason, topic

    def test_a_failure_with_no_text_is_named_by_its_class(self) -> None:
        assert describe_instructor_failure(instructor_exc=_wrapped(cause=RuntimeError())) == "RuntimeError"
