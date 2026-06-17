import pytest

from pipelex.core.pipes.pipe_blueprint import PIPE_SIGNATURE_TYPE_TAG, PipeCategory, PipeType


class TestPipeSignatureTaxonomyEviction:
    def test_signature_tag_value(self) -> None:
        assert PIPE_SIGNATURE_TYPE_TAG == "PipeSignature"

    def test_signature_tag_not_in_pipe_type(self) -> None:
        assert PIPE_SIGNATURE_TYPE_TAG not in PipeType.value_list()

    def test_signature_tag_not_in_pipe_category(self) -> None:
        assert PIPE_SIGNATURE_TYPE_TAG not in PipeCategory.value_list()

    def test_pipe_type_signature_member_removed(self) -> None:
        assert not hasattr(PipeType, "PIPE_SIGNATURE")

    def test_pipe_category_signature_member_removed(self) -> None:
        assert not hasattr(PipeCategory, "PIPE_SIGNATURE")

    def test_coercing_signature_tag_to_pipe_type_raises(self) -> None:
        with pytest.raises(ValueError, match="PipeSignature"):
            PipeType(PIPE_SIGNATURE_TYPE_TAG)

    def test_signature_tag_is_not_controller(self) -> None:
        assert PipeCategory.is_controller_by_str(PIPE_SIGNATURE_TYPE_TAG) is False

    def test_signature_tag_is_not_operator(self) -> None:
        # `is_controller_by_str` returning False must NOT be read as "therefore an operator": the
        # signature tag is outside the controller/operator dichotomy entirely. There is no
        # `is_operator_by_str`, so "not an operator" is shown by the tag coercing to no
        # `PipeCategory` member at all — it is neither operator nor controller.
        with pytest.raises(ValueError, match="PipeSignature"):
            PipeCategory(PIPE_SIGNATURE_TYPE_TAG)
