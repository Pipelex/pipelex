import pytest

from pipelex.base_exceptions import DisclosureMode, ErrorDomain, PipelexError
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError, BundleResourcePathError


class TestBundleResourceExceptions:
    @pytest.mark.parametrize("error_class", [BundleResourceNotNamedError, BundleResourcePathError])
    def test_a_refusal_of_the_files_sent_says_running_it_again_cannot_succeed(self, error_class: type[PipelexError]) -> None:
        """Deterministic refusals of what the caller sent, so their problem documents carry `retryable: false`."""
        report = error_class("The files sent are refused.").to_error_report()

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

    def test_an_error_that_declares_nothing_carries_no_retryable(self) -> None:
        report = PipelexError("Something failed.").to_error_report()

        assert report.retryable is None
        assert "retryable" not in report.to_dict()
