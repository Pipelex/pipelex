"""The input-format error family: a file input whose format its slot or its consumer cannot take.

Its messages carry only what the caller supplied (the input's path, the file's type) and what the
method declares, so they are caller-facing and survive STRICT disclosure, where a placeholder would
leave the caller with nothing to act on. The family sits in the input domain, so an API answers 422.
"""

import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorDomain, error_domain_to_http_status
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.pipeline.exceptions import PipelineInputContentError, PipelineInputFormatError, PipelineInputNotAnImageError

NOT_AN_IMAGE_MESSAGE = (
    "Input 'referral_letter' expects an image, but the file is a PDF document (application/pdf). Give an image file such as PNG, JPEG or WebP."
)


class TestPipelineInputFormatErrors:
    @pytest.mark.parametrize("error_class", [PipelineInputFormatError, PipelineInputNotAnImageError])
    def test_the_family_is_an_input_content_error_the_caller_can_fix(self, error_class: type[PipelineInputFormatError]):
        error = error_class(NOT_AN_IMAGE_MESSAGE)

        assert isinstance(error, PipelineInputContentError)
        assert error.error_domain == ErrorDomain.INPUT
        assert error_domain_to_http_status(error.error_domain) == 422
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT

    def test_not_an_image_is_a_format_error(self):
        assert issubclass(PipelineInputNotAnImageError, PipelineInputFormatError)

    @pytest.mark.parametrize("error_class", [PipelineInputFormatError, PipelineInputNotAnImageError])
    def test_the_message_survives_strict_disclosure(self, error_class: type[PipelineInputFormatError]):
        strict = error_class(NOT_AN_IMAGE_MESSAGE).to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)

        assert strict["message"] == NOT_AN_IMAGE_MESSAGE
        assert strict["message"] != INTERNAL_ERROR_PLACEHOLDER
