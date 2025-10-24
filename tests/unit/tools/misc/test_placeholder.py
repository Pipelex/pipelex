from pipelex.tools.misc.placeholder import PLACEHOLDER_PREFIX, make_placeholder_value, value_is_placeholder


class TestPlaceholder:
    def test_value_is_placeholder_valid_placeholder(self):
        """Test that values starting with the prefix are identified as placeholders."""
        result = value_is_placeholder(make_placeholder_value("TEST_VAR"))
        assert result is True

    def test_value_is_placeholder_exact_prefix_match(self):
        """Test that exact prefix match is identified as a placeholder."""
        result = value_is_placeholder(PLACEHOLDER_PREFIX)
        assert result is True

    def test_value_is_placeholder_non_placeholder(self):
        """Test that regular values are not identified as placeholders."""
        result = value_is_placeholder("regular_value")
        assert result is False

    def test_value_is_placeholder_prefix_in_middle(self):
        """Test that values with prefix not at start are not identified as placeholders."""
        result = value_is_placeholder(f"prefix-{PLACEHOLDER_PREFIX}-suffix")
        assert result is False

    def test_value_is_placeholder_none_value(self):
        """Test that None values are not identified as placeholders."""
        result = value_is_placeholder(None)
        assert result is False

    def test_value_is_placeholder_empty_string(self):
        """Test that empty strings are not identified as placeholders."""
        result = value_is_placeholder("")
        assert result is False

    def test_value_is_placeholder_partial_prefix_match(self):
        """Test that partial prefix matches are not identified as placeholders."""
        partial_prefix = PLACEHOLDER_PREFIX[:-3]  # Remove last 3 characters
        result = value_is_placeholder(f"{partial_prefix}-for-TEST")
        assert result is False

    def test_make_placeholder_value_basic(self):
        """Test that make_placeholder_value creates the correct format."""
        result = make_placeholder_value("TEST_VAR")
        assert result == "placeholder-for-TEST_VAR"

    def test_make_placeholder_value_different_keys(self):
        """Test make_placeholder_value with different key formats."""
        assert make_placeholder_value("OPENAI_API_KEY") == "placeholder-for-OPENAI_API_KEY"
        assert make_placeholder_value("simple_key") == "placeholder-for-simple_key"
        assert make_placeholder_value("Key123") == "placeholder-for-Key123"

    def test_make_placeholder_value_empty_key(self):
        """Test make_placeholder_value with empty key."""
        result = make_placeholder_value("")
        assert result == "placeholder-for-"

    def test_make_placeholder_value_special_characters(self):
        """Test make_placeholder_value with keys containing special characters."""
        assert make_placeholder_value("KEY_WITH_UNDERSCORES") == "placeholder-for-KEY_WITH_UNDERSCORES"
        assert make_placeholder_value("key-with-dashes") == "placeholder-for-key-with-dashes"
        assert make_placeholder_value("key.with.dots") == "placeholder-for-key.with.dots"

    def test_make_placeholder_value_integration_with_value_is_placeholder(self):
        """Test that make_placeholder_value output is correctly identified by value_is_placeholder."""
        test_keys = ["TEST1", "TEST2", "ANOTHER_KEY"]
        for key in test_keys:
            placeholder_value = make_placeholder_value(key)
            assert value_is_placeholder(placeholder_value), f"Failed for key: {key}"

    def test_placeholder_prefix_constant(self):
        """Test that the placeholder prefix constant has the expected value."""
        assert PLACEHOLDER_PREFIX == "placeholder"
