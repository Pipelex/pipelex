"""How a ``PipelexError`` resolves the registry code its problem carries, and what the code decides on the problem."""

import itertools
import re

import pytest
from mthds.protocol.problem.registry import CORE_CODE_SPECS, CoreCode, ProblemDomain, RetryVerdict

from pipelex.base_exceptions import PipelexConfigError, PipelexError, PipelexUnexpectedError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeSet, InheritsCause
from pipelex.errors.error_codes import error_code_spec, parse_error_code
from pipelex.errors.problem import PipelexProblem, ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class _ModelUnknownError(PipelexError):
    error_code = CoreCode.MODEL_UNKNOWN


class _FunctionRaisedError(PipelexError):
    error_code = CoreCode.PIPE_FUNCTION_RAISED


class _WrapperError(PipelexError):
    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.PIPE_INPUT_UNRESOLVED,))


class _InputWrapperError(PipelexError):
    error_code = InheritsCause(fallback=CoreCode.INPUT_INVALID)


class _ProviderError(PipelexError):
    error_code = ErrorCodeSet(default=CoreCode.PROVIDER_FAILED, others=(CoreCode.PROVIDER_RATE_LIMITED, CoreCode.PROVIDER_UNAVAILABLE))


class _AbstractBaseError(PipelexError):
    error_code = ABSTRACT_ERROR


def _raise_chain(*errors: BaseException) -> BaseException:
    """Chain ``errors`` outermost first, each raised from the next, and return the outermost."""
    for outer, inner in itertools.pairwise(errors):
        outer.__cause__ = inner
    return errors[0]


class TestErrorCodeResolution:
    def test_a_class_code_decides_the_problem(self) -> None:
        problem = _ModelUnknownError("no such model").to_problem(view=ProblemView.CALLER)
        spec = CORE_CODE_SPECS[CoreCode.MODEL_UNKNOWN]
        assert problem.code == CoreCode.MODEL_UNKNOWN
        assert problem.title == spec.title
        assert problem.type == f"https://mthds.ai/errors/{CoreCode.MODEL_UNKNOWN}"
        assert problem.domain == ProblemDomain.METHOD
        assert problem.retry == RetryVerdict.NO

    def test_a_pipelex_code_points_at_the_pipelex_docs(self) -> None:
        problem = PipelexConfigError("bad config").to_problem(view=ProblemView.CALLER)
        assert problem.code == PipelexErrorCode.CONFIG_INVALID
        assert problem.type == f"https://docs.pipelex.com/errors/{PipelexErrorCode.CONFIG_INVALID}"
        assert problem.title == error_code_spec(PipelexErrorCode.CONFIG_INVALID).title
        assert problem.domain == ProblemDomain.OPERATOR

    def test_a_raise_site_chooses_from_the_set(self) -> None:
        assert _ProviderError("boom").to_problem(view=ProblemView.CALLER).code == CoreCode.PROVIDER_FAILED
        chosen = _ProviderError("slow down").with_error_code(CoreCode.PROVIDER_RATE_LIMITED).to_problem(view=ProblemView.CALLER)
        assert chosen.code == CoreCode.PROVIDER_RATE_LIMITED
        assert chosen.is_retryable is True

    def test_a_raise_site_cannot_choose_a_code_its_class_does_not_declare(self) -> None:
        with pytest.raises(ValueError, match=re.escape("does not declare the code 'model.unknown'")):
            _ProviderError("boom").with_error_code(CoreCode.MODEL_UNKNOWN)

    def test_an_inheriting_wrapper_takes_its_cause_code(self) -> None:
        error = _raise_chain(_WrapperError("outer"), _ModelUnknownError("inner"))
        assert isinstance(error, PipelexError)
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.MODEL_UNKNOWN
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "_WrapperError"
        assert problem.diagnostics.message == "outer"

    def test_the_walk_stops_at_the_first_class_that_declares_a_code(self) -> None:
        error = _raise_chain(_WrapperError("outer"), _FunctionRaisedError("the function raised"), _ModelUnknownError("inside the function"))
        assert isinstance(error, PipelexError)
        assert error.resolve_error_code() == CoreCode.PIPE_FUNCTION_RAISED

    def test_a_chosen_code_stops_the_walk_at_an_inheriting_wrapper(self) -> None:
        error = _raise_chain(_WrapperError("outer").with_error_code(CoreCode.PIPE_INPUT_UNRESOLVED), _ModelUnknownError("inner"))
        assert isinstance(error, PipelexError)
        assert error.resolve_error_code() == CoreCode.PIPE_INPUT_UNRESOLVED

    def test_a_foreign_cause_gives_the_deepest_fallback(self) -> None:
        error = _raise_chain(_WrapperError("outer"), _InputWrapperError("inner"), KeyError("raw"))
        assert isinstance(error, PipelexError)
        assert error.resolve_error_code() == CoreCode.INPUT_INVALID

    def test_no_code_anywhere_is_the_catch_all(self) -> None:
        assert _AbstractBaseError("raised by mistake").resolve_error_code() == CoreCode.RUNTIME_UNEXPECTED
        assert PipelexError("bare root").to_problem(view=ProblemView.CALLER).code == CoreCode.RUNTIME_UNEXPECTED

    def test_an_abstract_wrapper_keeps_walking(self) -> None:
        error = _raise_chain(_AbstractBaseError("outer"), _ModelUnknownError("inner"))
        assert isinstance(error, PipelexError)
        assert error.resolve_error_code() == CoreCode.MODEL_UNKNOWN

    def test_a_cyclic_cause_chain_terminates(self) -> None:
        outer = _WrapperError("outer")
        inner = _InputWrapperError("inner")
        outer.__cause__ = inner
        inner.__cause__ = outer
        assert outer.resolve_error_code() == CoreCode.INPUT_INVALID

    def test_the_view_does_not_change_the_code(self) -> None:
        error = PipelexUnexpectedError("ours")
        assert error.to_problem(view=ProblemView.CALLER).code == error.to_problem(view=ProblemView.OPERATOR).code == CoreCode.RUNTIME_UNEXPECTED
        assert error.to_problem(view=ProblemView.CALLER).domain == ProblemDomain.RUNTIME

    def test_a_declaration_of_the_wrong_type_refuses_the_class(self) -> None:
        with pytest.raises(TypeError, match="error_code must be"):
            type("_StringCodeError", (PipelexError,), {"error_code": "model.unknown"})

    def test_round_trip_preserves_the_code(self) -> None:
        problem = PipelexConfigError("config gone").with_error_code(PipelexErrorCode.CONFIG_SYNTAX).to_problem(view=ProblemView.OPERATOR)
        recovered = PipelexProblem.model_validate(problem.to_wire())
        assert recovered.code == PipelexErrorCode.CONFIG_SYNTAX
        assert recovered.to_wire() == problem.to_wire()


class TestParseErrorCode:
    def test_a_core_code(self) -> None:
        assert parse_error_code("model.unknown") == CoreCode.MODEL_UNKNOWN

    def test_a_pipelex_code(self) -> None:
        assert parse_error_code("pipelex.config.invalid") == PipelexErrorCode.CONFIG_INVALID

    def test_an_unregistered_string(self) -> None:
        assert parse_error_code("not.a.code") is None
