from pipelex.core.pipes.pipe_blueprint import PipeCategory, PipeType


class TestPipeSignatureEnums:
    def test_pipe_type_pipe_signature_value(self) -> None:
        assert PipeType.PIPE_SIGNATURE == "PipeSignature"

    def test_pipe_type_pipe_signature_in_value_list(self) -> None:
        assert "PipeSignature" in PipeType.value_list()

    def test_pipe_type_pipe_signature_category(self) -> None:
        assert PipeType("PipeSignature").category is PipeCategory.PIPE_SIGNATURE

    def test_pipe_category_pipe_signature_value(self) -> None:
        assert PipeCategory.PIPE_SIGNATURE == "PipeSignature"

    def test_pipe_category_signature_is_not_controller(self) -> None:
        assert PipeCategory.is_controller_by_str("PipeSignature") is False
