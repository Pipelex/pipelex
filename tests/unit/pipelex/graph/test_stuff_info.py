"""Unit tests for the StuffInfo model."""

from pipelex.graph.graph_analysis import StuffInfo


class TestStuffInfo:
    """Tests for the StuffInfo model."""

    def test_stuff_info_with_string_data(self) -> None:
        """Test StuffInfo with string data."""
        info = StuffInfo(name="output", concept="Text", data="string content")
        assert info.name == "output"
        assert info.concept == "Text"
        assert info.data == "string content"

    def test_stuff_info_with_dict_data(self) -> None:
        """Test StuffInfo with dict data."""
        dict_data = {"key": "value", "nested": {"inner": 123}}
        info = StuffInfo(name="output", concept="Object", data=dict_data)
        assert info.data == dict_data

    def test_stuff_info_with_list_data(self) -> None:
        """Test StuffInfo with list data."""
        list_data = ["item1", "item2", "item3"]
        info = StuffInfo(name="output", concept="List", data=list_data)
        assert info.data == list_data

    def test_stuff_info_with_none_data(self) -> None:
        """Test StuffInfo with None data."""
        info = StuffInfo(name="output", concept="Text", data=None)
        assert info.data is None

    def test_stuff_info_optional_fields(self) -> None:
        """Test StuffInfo with only required fields."""
        info = StuffInfo(name="output")
        assert info.name == "output"
        assert info.concept is None
        assert info.data is None
