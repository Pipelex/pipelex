import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, RetryVerdict

from pipelex.base_exceptions import PipelexError
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError, BundleResourcePathError
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.problem import ProblemView


class TestBundleResourceExceptions:
    @pytest.mark.builds_problems_without_required_params(reason="builds each refusal with a message alone, to check its retry verdict")
    @pytest.mark.parametrize(
        ("error_class", "expected_code"),
        [
            (BundleResourceNotNamedError, CoreCode.REQUEST_INVALID),
            (BundleResourcePathError, CoreCode.SECURITY_INPUT_PATH_REFUSED),
        ],
    )
    def test_a_refusal_of_the_files_sent_says_running_it_again_cannot_succeed(
        self, error_class: type[PipelexError], expected_code: ErrorCode
    ) -> None:
        """Deterministic refusals of what the caller sent, so their problem documents carry `retry: no` in either view."""
        error = error_class("The files sent are refused.")

        for view in (ProblemView.CALLER, ProblemView.OPERATOR):
            problem = error.to_problem(view=view)
            assert problem.code == expected_code
            assert problem.domain == ProblemDomain.INPUT
            assert problem.retry == RetryVerdict.NO
            assert problem.to_wire()["retry"] == "no"

    @pytest.mark.builds_problems_without_required_params(reason="builds the refusal with a message alone, to check what its wrapper reports")
    def test_a_wrapper_raised_from_one_carries_its_code_and_retry(self) -> None:
        try:
            try:
                cause_msg = "A file no step names."
                raise BundleResourceNotNamedError(cause_msg)
            except BundleResourceNotNamedError as exc:
                msg = "The library could not be loaded."
                raise PipelexError(msg) from exc
        except PipelexError as wrapper:
            problem = wrapper.to_problem(view=ProblemView.OPERATOR)

        assert problem.code == CoreCode.REQUEST_INVALID
        assert problem.retry == RetryVerdict.NO
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "PipelexError"
        assert [cause.error_class for cause in problem.diagnostics.causes or []] == ["BundleResourceNotNamedError"]

    @pytest.mark.builds_problems_without_required_params(reason="builds the refusal with a message alone, to check the code its raise site chooses")
    def test_two_paths_naming_one_file_are_an_invalid_request(self) -> None:
        """A raise site that refuses paths that cannot make one tree chooses the request's code, not the path refusal's."""
        problem = BundleResourcePathError("Two files name one file.").with_error_code(CoreCode.REQUEST_INVALID).to_problem(view=ProblemView.CALLER)

        assert problem.code == CoreCode.REQUEST_INVALID
        assert problem.domain == ProblemDomain.INPUT
        assert problem.retry == RetryVerdict.NO
