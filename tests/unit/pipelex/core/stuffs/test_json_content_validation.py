import pytest

from pipelex.core.stuffs.json_content import JSONContent


class TestJSONContentValidation:
    """Test JSONContent validation."""

    def test_valid_complex_json(self):
        """Test creating JSONContent with a complex structure."""
        json_obj = {
            "id": "123",
            "metadata": {
                "created": "2024-01-01",
                "updated": "2024-01-02",
                "tags": ["important", "urgent"],
            },
            "data": [
                {"name": "item1", "count": 10},
                {"name": "item2", "count": 20},
            ],
            "active": True,
            "score": 95.5,
        }
        content = JSONContent(json_obj=json_obj)
        assert content.json_obj == json_obj

    def test_invalid_json_with_non_serializable_object(self):
        """Test that non-JSON-serializable objects raise TypeError."""

        class NonSerializable:
            pass

        json_obj = {"object": NonSerializable()}

        with pytest.raises(TypeError, match="json_obj is not valid JSON"):
            JSONContent(json_obj=json_obj)

    def test_invalid_json_with_non_serializable_function(self):
        """Test that functions in JSON object raise TypeError."""

        def some_function():
            pass

        json_obj = {"func": some_function}

        with pytest.raises(TypeError, match="json_obj is not valid JSON"):
            JSONContent(json_obj=json_obj)

    def test_invalid_json_with_set(self):
        """Test that sets in JSON object raise TypeError."""
        json_obj = {"data": {1, 2, 3}}

        with pytest.raises(TypeError, match="json_obj is not valid JSON"):
            JSONContent(json_obj=json_obj)
