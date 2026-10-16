import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import DisclosureMode, ErrorDomain, PipelexError
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError, BundleResourcePathError
from pipelex.errors.error_codes import ErrorCode


class TestBundleResourceExceptions:
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
        """Deterministic refusals of what the caller sent, so their problem documents carry `retryable: false`."""
        report = error_class("The files sent are refused.").to_error_report()

        assert report.code == expected_code
        assert report.retryable is False
        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message is True
        assert report.to_dict()["retryable"] is False
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["retryable"] is False

    def test_a_wrapper_raised_from_one_carries_its_retryable(self) -> None:
        try:
            try:
                cause_msg = "A file no step names."
                raise BundleResourceNotNamedError(cause_msg)
            except BundleResourceNotNamedError as exc:
                msg = "The library could not be loaded."
                raise PipelexError(msg) from exc
        except PipelexError as wrapper:
            report = wrapper.to_error_report()

        assert report.error_type == "PipelexError"
        assert report.retryable is False

    def test_two_paths_naming_one_file_are_an_invalid_request(self) -> None:
        """A raise site that refuses paths that cannot make one tree chooses the request's code, not the path refusal's."""
        report = BundleResourcePathError("Two files name one file.").with_error_code(CoreCode.REQUEST_INVALID).to_error_report()

        assert report.code == CoreCode.REQUEST_INVALID
        assert report.error_domain == ErrorDomain.INPUT
        assert report.retryable is False
