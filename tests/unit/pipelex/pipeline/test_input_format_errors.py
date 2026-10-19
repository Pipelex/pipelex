"""The input-format error family: a file input whose format its slot or its consumer cannot take.

The family sits in the input domain, so an API answers 422, and the caller is told to change the input. Its messages
are the operator's diagnostics; the caller reads the sentence its code renders from the parameters the raise site
gives, the input, the file's format and the model, which leave the caller something to act on.
"""

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind

from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import (
    PipelineInputContentError,
    PipelineInputFormatError,
    PipelineInputFormatUnsupportedError,
    PipelineInputNotAnImageError,
)

NOT_AN_IMAGE_MESSAGE = (
    "Input 'referral_letter' expects an image, but the file is a PDF document (.pdf). Give an image file such as PNG, JPEG or WebP."
)


class TestPipelineInputFormatErrors:
    @pytest.mark.builds_problems_without_required_params(reason="builds each class with a message alone, to check the code and advice of the family")
    @pytest.mark.parametrize("error_class", [PipelineInputNotAnImageError, PipelineInputFormatUnsupportedError])
    def test_the_family_is_an_input_content_error_the_caller_can_fix(self, error_class: type[PipelineInputFormatError]):
        error = error_class(NOT_AN_IMAGE_MESSAGE)
        problem = error.to_problem(view=ProblemView.CALLER)

        assert isinstance(error, PipelineInputContentError)
        assert problem.code == CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
        assert problem.domain == ProblemDomain.INPUT
        assert error_code_spec(CoreCode.INPUT_FILE_TYPE_UNSUPPORTED).status == 422
        assert problem.next_step.kind == StepKind.CHANGE_INPUT
        advice = error.advised_action()
        assert advice is not None
        assert advice.kind == UserActionKind.CHANGE_INPUT

    def test_not_an_image_is_a_format_error(self):
        assert issubclass(PipelineInputNotAnImageError, PipelineInputFormatError)

    @pytest.mark.parametrize("error_class", [PipelineInputNotAnImageError, PipelineInputFormatUnsupportedError])
    def test_the_caller_reads_the_code_s_sentence_and_the_operator_the_message(self, error_class: type[PipelineInputFormatError]):
        error = error_class(NOT_AN_IMAGE_MESSAGE).with_params(input="referral_letter", format="application/pdf", model="vision-model")

        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.detail == "The model 'vision-model' cannot take the file of the input 'referral_letter', whose format is 'application/pdf'."
        assert NOT_AN_IMAGE_MESSAGE not in str(caller.to_wire())
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.message == NOT_AN_IMAGE_MESSAGE
