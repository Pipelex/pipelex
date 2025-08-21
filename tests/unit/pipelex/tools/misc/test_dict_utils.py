"""Unit tests for dict_utils module."""

from pipelex.tools.misc.dict_utils import insert_before


class TestDictUtils:
    """Test class for dict_utils functions."""

    def test_insert_before_basic(self) -> None:
        """Test basic insert_before functionality."""
        original = {"a": 1, "c": 3}
        result = insert_before(original, "c", "b", 2)

        expected_keys = ["a", "b", "c"]
        assert list(result.keys()) == expected_keys
        assert result["a"] == 1
        assert result["b"] == 2
        assert result["c"] == 3
        assert original != result  # Should return new dict, not modify original

    def test_insert_before_target_not_found(self) -> None:
        """Test insert_before when target key doesn't exist."""
        original = {"a": 1, "b": 2}
        result = insert_before(original, "z", "c", 3)

        expected_keys = ["a", "b", "c"]
        assert list(result.keys()) == expected_keys
        assert result["c"] == 3

    def test_preserve_original_dict(self) -> None:
        """Test that original dictionary is not modified."""
        original = {"a": 1, "b": 2, "c": 3}
        original_copy = original.copy()

        insert_before(original, "b", "x", 999)

        assert original == original_copy

    def test_complex_nested_structure(self) -> None:
        """Test with complex nested dictionary structure."""
        original = {"type": "PipeLLM", "definition": "Test pipe", "output": "Text", "system_prompt": "Test prompt"}

        # Insert inputs before output
        result = insert_before(original, "output", "inputs", "InputText")

        expected_keys = ["type", "definition", "inputs", "output", "system_prompt"]
        assert list(result.keys()) == expected_keys
        assert result["inputs"] == "InputText"
