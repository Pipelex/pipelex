from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class TestCustomBaseModel:
    """Tests for CustomBaseModel class."""

    def test_custom_base_model_truncates_repr(self) -> None:
        """Test that CustomBaseModel truncates long base64 and URL strings in repr output."""

        class TestModel(CustomBaseModel):
            base_64: str
            url: str
            other: str

        AttributePolisher.base_64_truncate_length = 10
        AttributePolisher.url_truncate_length = 10
        model = TestModel(
            base_64="b" * 20,
            url="data:image/png;base64," + "x" * 20,
            other="val",
        )
        repr_str = repr(model)
        assert "bbbbbbbbbb…" in repr_str
        assert "data:image…" in repr_str
