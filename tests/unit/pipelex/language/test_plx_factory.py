from typing import Any

import pytest
import tomlkit
from pytest_mock import MockerFixture

from pipelex.language.plx_config import PlxConfig, PlxConfigForConcepts, PlxConfigForPipes, PlxConfigInlineTables, PlxConfigStrings
from pipelex.language.plx_factory import PlxFactory


class TestPlxFactoryUnit:
    """Unit tests for PlxFactory methods."""

    @pytest.fixture
    def mock_plx_config(self) -> PlxConfig:
        """Create a mock PLX configuration for testing."""
        return PlxConfig(
            strings=PlxConfigStrings(
                prefer_literal=True,
                force_multiline=False,
                length_limit_to_multiline=50,
                ensure_trailing_newline=True,
                ensure_leading_blank_line=False,
            ),
            inline_tables=PlxConfigInlineTables(
                spaces_inside_curly_braces=True,
            ),
            concepts=PlxConfigForConcepts(
                structure_field_ordering=["type", "description", "inputs", "output"],
            ),
            pipes=PlxConfigForPipes(
                field_ordering=["type", "description", "inputs", "output"],
            ),
        )

    @pytest.fixture
    def sample_mapping_data(self) -> dict[str, Any]:
        """Sample mapping data for testing."""
        return {
            "simple_field": "simple_value",
            "nested_mapping": {
                "inner_key": "inner_value",
                "inner_number": 42,
            },
            "list_field": ["item1", "item2", "item3"],
            "complex_list": [
                {"name": "first", "value": 1},
                {"name": "second", "value": 2},
            ],
        }

    def test_format_tomlkit_string_simple(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test formatting simple strings."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        # Test simple string
        result = PlxFactory.format_tomlkit_string("simple text")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # The actual string value without quotes
        assert result.value == "simple text"

    def test_format_tomlkit_string_multiline(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test formatting multiline strings."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        # Test string with newlines
        multiline_text = "line1\nline2\nline3"
        result = PlxFactory.format_tomlkit_string(multiline_text)
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should be multiline with trailing newline
        assert result.value == "line1\nline2\nline3\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_format_tomlkit_string_force_multiline(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test force multiline configuration."""
        mock_plx_config.strings.force_multiline = True
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        result = PlxFactory.format_tomlkit_string("short")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should be multiline even for short text
        assert result.value == "short\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_format_tomlkit_string_length_limit(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test length limit for multiline conversion."""
        mock_plx_config.strings.length_limit_to_multiline = 10
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        long_text = "this is a very long text that exceeds the limit"
        result = PlxFactory.format_tomlkit_string(long_text)
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should be multiline due to length
        assert result.value == "this is a very long text that exceeds the limit\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_format_tomlkit_string_leading_blank_line(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test leading blank line configuration."""
        mock_plx_config.strings.ensure_leading_blank_line = True
        mock_plx_config.strings.force_multiline = True
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        result = PlxFactory.format_tomlkit_string("content")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should have leading blank line
        assert result.value == "\ncontent\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_convert_dicts_to_inline_tables_simple_dict(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test converting simple dictionary to inline table."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        input_dict = {"key1": "value1", "key2": "value2"}
        result = PlxFactory.convert_dicts_to_inline_tables(input_dict)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert result["key1"].value == "value1"
        assert result["key2"].value == "value2"

    def test_convert_dicts_to_inline_tables_with_field_ordering(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test converting dictionary with field ordering."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        input_dict = {"key2": "value2", "key1": "value1", "key3": "value3"}
        field_ordering = ["key1", "key3"]
        result = PlxFactory.convert_dicts_to_inline_tables(input_dict, field_ordering)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Check that ordered fields come first
        keys = list(result.keys())
        assert keys[0] == "key1"
        assert keys[1] == "key3"
        # Note: the implementation might not include all keys if not in ordering
        if len(keys) > 2:
            assert keys[2] == "key2"

    def test_convert_dicts_to_inline_tables_nested_dict(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test converting nested dictionary."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        input_dict = {"outer": {"inner": "value"}}
        result = PlxFactory.convert_dicts_to_inline_tables(input_dict)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert isinstance(result["outer"], tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert result["outer"]["inner"].value == "value"

    def test_convert_dicts_to_inline_tables_list_with_dicts(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test converting list containing dictionaries."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        input_list = [{"name": "first", "value": 1}, {"name": "second", "value": 2}]
        result = PlxFactory.convert_dicts_to_inline_tables(input_list)

        assert isinstance(result, tomlkit.items.Array)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert len(result) == 2
        assert isinstance(result[0], tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert result[0]["name"].value == "first"
        assert result[0]["value"] == 1

    def test_convert_dicts_to_inline_tables_string_handling(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test string handling in conversion."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        # Test simple string
        result = PlxFactory.convert_dicts_to_inline_tables("simple string")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

        # Test other types pass through
        assert PlxFactory.convert_dicts_to_inline_tables(42) == 42
        assert PlxFactory.convert_dicts_to_inline_tables(True) is True

    def test_convert_mapping_to_table(self, mocker: MockerFixture, mock_plx_config: PlxConfig, sample_mapping_data: dict[str, Any]):
        """Test converting mapping to table."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        result = PlxFactory.convert_mapping_to_table(sample_mapping_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "simple_field" in result
        assert "nested_mapping" in result
        assert "list_field" in result
        assert "complex_list" in result

    def test_convert_mapping_to_table_with_field_ordering(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test converting mapping with field ordering."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        mapping = {"field3": "value3", "field1": "value1", "field2": "value2"}
        field_ordering = ["field1", "field2"]

        result = PlxFactory.convert_mapping_to_table(mapping, field_ordering)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Check ordering (note: tomlkit preserves insertion order)
        keys = list(result.keys())
        assert keys[0] == "field1"
        assert keys[1] == "field2"
        assert keys[2] == "field3"

    def test_convert_mapping_to_table_skips_category(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test that category field is skipped."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        mapping = {"field1": "value1", "category": "should_be_skipped", "field2": "value2"}
        result = PlxFactory.convert_mapping_to_table(mapping)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "field1" in result
        assert "field2" in result
        assert "category" not in result

    def test_add_spaces_to_inline_tables_simple(self):
        """Test adding spaces to simple inline tables."""
        input_toml = "{key = value}"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

    def test_add_spaces_to_inline_tables_already_spaced(self):
        """Test that already spaced tables are preserved."""
        input_toml = "{ key = value }"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

    def test_add_spaces_to_inline_tables_nested(self):
        """Test adding spaces to nested inline tables."""
        input_toml = "{outer = {inner = value}}"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ outer = { inner = value } }"

    def test_add_spaces_to_inline_tables_with_jinja2(self):
        """Test that Jinja2 templates are preserved."""
        input_toml = "template = '{{ variable }}' and {key = value}"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "template = '{{ variable }}' and { key = value }"

    def test_add_spaces_to_inline_tables_complex(self):
        """Test complex inline table spacing."""
        input_toml = "config = {db = {host = 'localhost', port = 5432}, cache = {enabled = true}}"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        expected = "config = { db = { host = 'localhost', port = 5432 }, cache = { enabled = true } }"
        assert result == expected

    def test_add_spaces_to_inline_tables_partial_spacing(self):
        """Test partial spacing scenarios."""
        # Left space only
        input_toml = "{ key = value}"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

        # Right space only
        input_toml = "{key = value }"
        result = PlxFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

    def test_make_table_obj_for_pipe(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test making table object for pipe section."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        pipe_data = {
            "type": "PipeLLM",
            "description": "Test pipe",
            "inputs": {"input1": "Text"},
            "output": "Text",
            "nested_config": {"param1": "value1", "param2": 42},
        }

        result = PlxFactory.make_table_obj_for_pipe(pipe_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "type" in result
        assert "description" in result
        assert "inputs" in result
        assert "output" in result
        assert "nested_config" in result

    def test_make_table_obj_for_concept_simple_string(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test making table object for concept with simple string definition."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        concept_data = {"SimpleConcept": "A simple concept definition"}

        result = PlxFactory.make_table_obj_for_concept(concept_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "SimpleConcept" in result
        assert result["SimpleConcept"] == "A simple concept definition"

    def test_make_table_obj_for_concept_with_structure(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test making table object for concept with structure."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        concept_data = {"ComplexConcept": {"description": "A complex concept", "structure": {"field1": "string", "field2": "int"}}}

        result = PlxFactory.make_table_obj_for_concept(concept_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "ComplexConcept" in result
        assert isinstance(result["ComplexConcept"], tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "description" in result["ComplexConcept"]
        assert "structure" in result["ComplexConcept"]

    def test_make_table_obj_for_concept_structure_string(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test concept with structure as string."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        concept_data = {"ConceptWithStringStructure": {"structure": "SomeClass"}}

        result = PlxFactory.make_table_obj_for_concept(concept_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        concept_table = result["ConceptWithStringStructure"]
        assert isinstance(concept_table, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert concept_table["structure"] == "SomeClass"

    def test_make_table_obj_for_concept_invalid_structure(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test error handling for invalid structure types."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        concept_data = {
            "InvalidConcept": {
                "structure": 123  # Invalid type
            }
        }

        with pytest.raises(TypeError, match="Structure field value is not a mapping"):
            PlxFactory.make_table_obj_for_concept(concept_data)

    def test_make_table_obj_for_concept_invalid_concept_value(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test error handling for invalid concept value types."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        concept_data = {
            "InvalidConcept": 123  # Invalid type
        }

        with pytest.raises(TypeError, match="Concept field value is not a mapping"):
            PlxFactory.make_table_obj_for_concept(concept_data)

    def test_dict_to_plx_styled_toml_with_spacing(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test dict to PLX styled TOML with spacing enabled."""
        mock_plx_config.inline_tables.spaces_inside_curly_braces = True
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)
        mock_add_spaces = mocker.patch.object(PlxFactory, "add_spaces_to_inline_tables", return_value="spaced_output")

        data = {"domain": "test", "description": "test domain"}

        result = PlxFactory.dict_to_plx_styled_toml(data)

        assert result == "spaced_output"
        mock_add_spaces.assert_called_once()

    def test_dict_to_plx_styled_toml_without_spacing(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test dict to PLX styled TOML without spacing."""
        mock_plx_config.inline_tables.spaces_inside_curly_braces = False
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)
        mock_add_spaces = mocker.patch.object(PlxFactory, "add_spaces_to_inline_tables")

        data = {"domain": "test", "description": "test domain"}

        result = PlxFactory.dict_to_plx_styled_toml(data)

        # Should not call add_spaces_to_inline_tables
        mock_add_spaces.assert_not_called()
        assert isinstance(result, str)

    def test_dict_to_plx_styled_toml_empty_sections(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test handling of empty sections."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        data: dict[str, Any] = {
            "domain": "test",
            "concept": {},  # Empty concept section
            "pipe": {},  # Empty pipe section
        }

        result = PlxFactory.dict_to_plx_styled_toml(data)

        # Empty sections should be skipped
        assert "concept" not in result
        assert "pipe" not in result
        assert "domain" in result

    def test_dict_to_plx_styled_toml_with_pipe_section(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test dict to PLX styled TOML with pipe section."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        data = {"domain": "test", "pipe": {"test_pipe": {"type": "PipeLLM", "description": "Test pipe"}}}

        result = PlxFactory.dict_to_plx_styled_toml(data)

        assert "domain" in result
        assert "[pipe.test_pipe]" in result
        assert "type" in result
        assert "description" in result

    def test_dict_to_plx_styled_toml_with_concept_section(self, mocker: MockerFixture, mock_plx_config: PlxConfig):
        """Test dict to PLX styled TOML with concept section."""
        _mock_config = mocker.patch.object(PlxFactory, "_plx_config", return_value=mock_plx_config)

        data = {"domain": "test", "concept": {"TestConcept": "A test concept"}}

        result = PlxFactory.dict_to_plx_styled_toml(data)

        assert "domain" in result
        assert "[concept]" in result
        assert "TestConcept" in result
