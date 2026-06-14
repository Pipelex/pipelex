from typing import Any

import pytest
import tomlkit
from pytest_mock import MockerFixture

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.language.mthds_config import MthdsConfig, MthdsConfigForConcepts, MthdsConfigForPipes, MthdsConfigInlineTables, MthdsConfigStrings
from pipelex.language.mthds_factory import PIPE_CATEGORY_FIELD_KEY, MthdsFactory
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint


class TestMthdsFactoryUnit:
    """Unit tests for MthdsFactory methods."""

    @pytest.fixture
    def mock_mthds_config(self) -> MthdsConfig:
        """Create a mock MTHDS configuration for testing."""
        return MthdsConfig(
            strings=MthdsConfigStrings(
                prefer_literal=True,
                force_multiline=False,
                length_limit_to_multiline=50,
                ensure_trailing_newline=True,
                ensure_leading_blank_line=False,
            ),
            inline_tables=MthdsConfigInlineTables(
                spaces_inside_curly_braces=True,
            ),
            concepts=MthdsConfigForConcepts(
                structure_field_ordering=["type", "description", "inputs", "output"],
            ),
            pipes=MthdsConfigForPipes(
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

    def test_format_tomlkit_string_simple(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test formatting simple strings."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        # Test simple string
        result = MthdsFactory.format_tomlkit_string("simple text")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # The actual string value without quotes
        assert result.value == "simple text"

    def test_format_tomlkit_string_multiline(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test formatting multiline strings."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        # Test string with newlines
        multiline_text = "line1\nline2\nline3"
        result = MthdsFactory.format_tomlkit_string(multiline_text)
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should be multiline with trailing newline
        assert result.value == "line1\nline2\nline3\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_format_tomlkit_string_force_multiline(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test force multiline configuration."""
        mock_mthds_config.strings.force_multiline = True
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        result = MthdsFactory.format_tomlkit_string("short")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should be multiline even for short text
        assert result.value == "short\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_format_tomlkit_string_length_limit(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test length limit for multiline conversion."""
        mock_mthds_config.strings.length_limit_to_multiline = 10
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        long_text = "this is a very long text that exceeds the limit"
        result = MthdsFactory.format_tomlkit_string(long_text)
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should be multiline due to length
        assert result.value == "this is a very long text that exceeds the limit\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_format_tomlkit_string_leading_blank_line(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test leading blank line configuration."""
        mock_mthds_config.strings.ensure_leading_blank_line = True
        mock_mthds_config.strings.force_multiline = True
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        result = MthdsFactory.format_tomlkit_string("content")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Should have leading blank line
        assert result.value == "\ncontent\n"
        # Check if it's a multiline string by checking if it has newlines in the value
        assert "\n" in result.value

    def test_convert_dicts_to_inline_tables_simple_dict(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test converting simple dictionary to inline table."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        input_dict = {"key1": "value1", "key2": "value2"}
        result = MthdsFactory.convert_dicts_to_inline_tables(input_dict)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert result["key1"].value == "value1"
        assert result["key2"].value == "value2"

    def test_convert_dicts_to_inline_tables_with_field_ordering(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test converting dictionary with field ordering preserves all fields."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        input_dict = {"key2": "value2", "key1": "value1", "key3": "value3"}
        field_ordering = ["key1", "key3"]
        result = MthdsFactory.convert_dicts_to_inline_tables(input_dict, field_ordering=field_ordering)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # All input keys must be present in the result
        assert set(result.keys()) == set(input_dict.keys())
        # Ordered fields come first, remaining fields follow
        keys = list(result.keys())
        assert keys[0] == "key1"
        assert keys[1] == "key3"
        assert keys[2] == "key2"

    @pytest.mark.parametrize(
        ("topic", "input_dict", "field_ordering"),
        [
            (
                "concept_ref not in ordering",
                {"type": "str", "concept_ref": "MyConcept", "description": "A field referencing a concept"},
                ["type", "description"],
            ),
            (
                "item_concept_ref not in ordering",
                {"type": "list", "item_concept_ref": "ItemConcept", "description": "A list field"},
                ["type", "description"],
            ),
            (
                "multiple extra fields not in ordering",
                {"type": "str", "concept_ref": "MyConcept", "item_concept_ref": "ItemConcept", "required": True},
                ["type"],
            ),
            (
                "all fields in ordering",
                {"type": "str", "description": "A field", "required": True},
                ["type", "description", "required"],
            ),
            (
                "empty ordering",
                {"type": "str", "concept_ref": "MyConcept"},
                [],
            ),
        ],
    )
    def test_convert_dicts_to_inline_tables_with_field_ordering_preserves_all_fields(
        self,
        mocker: MockerFixture,
        mock_mthds_config: MthdsConfig,
        topic: str,
        input_dict: dict[str, Any],
        field_ordering: list[str],
    ):
        """Test that all input fields are preserved in the output regardless of field_ordering."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        result = MthdsFactory.convert_dicts_to_inline_tables(input_dict, field_ordering=field_ordering or None)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        result_keys = set(result.keys())
        input_keys = set(input_dict.keys())
        assert result_keys == input_keys, f"[{topic}] Fields lost during conversion: {input_keys - result_keys}"
        # Also verify values match
        for key, expected_value in input_dict.items():
            result_value = result[key]
            if isinstance(expected_value, str):
                assert result_value.value == expected_value, f"[{topic}] Value mismatch for key '{key}'"
            else:
                assert result_value == expected_value, f"[{topic}] Value mismatch for key '{key}'"

    def test_convert_dicts_to_inline_tables_nested_dict(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test converting nested dictionary."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        input_dict = {"outer": {"inner": "value"}}
        result = MthdsFactory.convert_dicts_to_inline_tables(input_dict)

        assert isinstance(result, tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert isinstance(result["outer"], tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert result["outer"]["inner"].value == "value"

    def test_convert_dicts_to_inline_tables_list_with_dicts(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test converting list containing dictionaries."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        input_list = [{"name": "first", "value": 1}, {"name": "second", "value": 2}]
        result = MthdsFactory.convert_dicts_to_inline_tables(input_list)

        assert isinstance(result, tomlkit.items.Array)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert len(result) == 2
        assert isinstance(result[0], tomlkit.items.InlineTable)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert result[0]["name"].value == "first"
        assert result[0]["value"] == 1

    def test_convert_dicts_to_inline_tables_string_handling(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test string handling in conversion."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        # Test simple string
        result = MthdsFactory.convert_dicts_to_inline_tables("simple string")
        assert isinstance(result, tomlkit.items.String)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

        # Test other types pass through
        assert MthdsFactory.convert_dicts_to_inline_tables(42) == 42
        assert MthdsFactory.convert_dicts_to_inline_tables(True) is True

    def test_convert_mapping_to_table(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig, sample_mapping_data: dict[str, Any]):
        """Test converting mapping to table."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        result = MthdsFactory.convert_mapping_to_table(sample_mapping_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "simple_field" in result
        assert "nested_mapping" in result
        assert "list_field" in result
        assert "complex_list" in result

    def test_convert_mapping_to_table_with_field_ordering(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test converting mapping with field ordering."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        mapping = {"field3": "value3", "field1": "value1", "field2": "value2"}
        field_ordering = ["field1", "field2"]

        result = MthdsFactory.convert_mapping_to_table(mapping, field_ordering=field_ordering)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        # Check ordering (note: tomlkit preserves insertion order)
        keys = list(result.keys())
        assert keys[0] == "field1"
        assert keys[1] == "field2"
        assert keys[2] == "field3"

    def test_convert_mapping_to_table_skips_category(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test that category field is skipped."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        mapping = {"field1": "value1", PIPE_CATEGORY_FIELD_KEY: "should_be_skipped", "field2": "value2"}
        result = MthdsFactory.convert_mapping_to_table(mapping)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "field1" in result
        assert "field2" in result
        assert PIPE_CATEGORY_FIELD_KEY not in result

    def test_add_spaces_to_inline_tables_simple(self):
        """Test adding spaces to simple inline tables."""
        input_toml = "{key = value}"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

    def test_add_spaces_to_inline_tables_already_spaced(self):
        """Test that already spaced tables are preserved."""
        input_toml = "{ key = value }"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

    def test_add_spaces_to_inline_tables_nested(self):
        """Test adding spaces to nested inline tables."""
        input_toml = "{outer = {inner = value}}"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ outer = { inner = value } }"

    def test_add_spaces_to_inline_tables_with_jinja2(self):
        """Test that Jinja2 templates are preserved."""
        input_toml = "template = '{{ variable }}' and {key = value}"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "template = '{{ variable }}' and { key = value }"

    def test_add_spaces_to_inline_tables_complex(self):
        """Test complex inline table spacing."""
        input_toml = "config = {db = {host = 'localhost', port = 5432}, cache = {enabled = true}}"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        expected = "config = { db = { host = 'localhost', port = 5432 }, cache = { enabled = true } }"
        assert result == expected

    def test_add_spaces_to_inline_tables_partial_spacing(self):
        """Test partial spacing scenarios."""
        # Left space only
        input_toml = "{ key = value}"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

        # Right space only
        input_toml = "{key = value }"
        result = MthdsFactory.add_spaces_to_inline_tables(input_toml)
        assert result == "{ key = value }"

    def test_make_table_obj_for_pipe(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test making table object for pipe section."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        pipe_data = {
            "type": "PipeLLM",
            "description": "Test pipe",
            "inputs": {"input1": "Text"},
            "output": "Text",
            "nested_config": {"param1": "value1", "param2": 42},
        }

        result = MthdsFactory.make_table_obj_for_pipe(pipe_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "type" in result
        assert "description" in result
        assert "inputs" in result
        assert "output" in result
        assert "nested_config" in result

    def test_make_table_obj_for_concept_simple_string(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test making table object for concept with simple string definition."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        concept_data = {"SimpleConcept": "A simple concept definition"}

        result = MthdsFactory.make_table_obj_for_concept(concept_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "SimpleConcept" in result
        assert result["SimpleConcept"] == "A simple concept definition"

    def test_make_table_obj_for_concept_with_structure(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test making table object for concept with structure."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        concept_data = {"ComplexConcept": {"description": "A complex concept", "structure": {"field1": "string", "field2": "int"}}}

        result = MthdsFactory.make_table_obj_for_concept(concept_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "ComplexConcept" in result
        assert isinstance(result["ComplexConcept"], tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert "description" in result["ComplexConcept"]
        assert "structure" in result["ComplexConcept"]

    def test_make_table_obj_for_concept_structure_string(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test concept with structure as string."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        concept_data = {"ConceptWithStringStructure": {"structure": "SomeClass"}}

        result = MthdsFactory.make_table_obj_for_concept(concept_data)

        assert isinstance(result, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        concept_table = result["ConceptWithStringStructure"]
        assert isinstance(concept_table, tomlkit.items.Table)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        assert concept_table["structure"] == "SomeClass"

    def test_make_table_obj_for_concept_invalid_structure(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test error handling for invalid structure types."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        concept_data = {
            "InvalidConcept": {
                "structure": 123  # Invalid type
            }
        }

        with pytest.raises(TypeError, match="Structure field value is not a mapping"):
            MthdsFactory.make_table_obj_for_concept(concept_data)

    def test_make_table_obj_for_concept_invalid_concept_value(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test error handling for invalid concept value types."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        concept_data = {
            "InvalidConcept": 123  # Invalid type
        }

        with pytest.raises(TypeError, match="Concept field value is not a mapping"):
            MthdsFactory.make_table_obj_for_concept(concept_data)

    def test_dict_to_mthds_styled_toml_with_spacing(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test dict to MTHDS styled TOML with spacing enabled."""
        mock_mthds_config.inline_tables.spaces_inside_curly_braces = True
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)
        mock_add_spaces = mocker.patch.object(MthdsFactory, "add_spaces_to_inline_tables", return_value="spaced_output")

        data = {"domain": "test", "description": "test domain"}

        result = MthdsFactory.dict_to_mthds_styled_toml(data)

        assert result == "spaced_output"
        mock_add_spaces.assert_called_once()

    def test_dict_to_mthds_styled_toml_without_spacing(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test dict to MTHDS styled TOML without spacing."""
        mock_mthds_config.inline_tables.spaces_inside_curly_braces = False
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)
        mock_add_spaces = mocker.patch.object(MthdsFactory, "add_spaces_to_inline_tables")

        data = {"domain": "test", "description": "test domain"}

        result = MthdsFactory.dict_to_mthds_styled_toml(data)

        # Should not call add_spaces_to_inline_tables
        mock_add_spaces.assert_not_called()
        assert isinstance(result, str)

    def test_dict_to_mthds_styled_toml_empty_sections(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test handling of empty sections."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        data: dict[str, Any] = {
            "domain": "test",
            "concept": {},  # Empty concept section
            "pipe": {},  # Empty pipe section
        }

        result = MthdsFactory.dict_to_mthds_styled_toml(data)

        # Empty sections should be skipped
        assert "concept" not in result
        assert "pipe" not in result
        assert "domain" in result

    def test_dict_to_mthds_styled_toml_with_pipe_section(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test dict to MTHDS styled TOML with pipe section."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        data = {"domain": "test", "pipe": {"test_pipe": {"type": "PipeLLM", "description": "Test pipe"}}}

        result = MthdsFactory.dict_to_mthds_styled_toml(data)

        assert "domain" in result
        assert "[pipe.test_pipe]" in result
        assert "type" in result
        assert "description" in result

    def test_dict_to_mthds_styled_toml_with_concept_section(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test dict to MTHDS styled TOML with concept section."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        data = {"domain": "test", "concept": {"TestConcept": "A test concept"}}

        result = MthdsFactory.dict_to_mthds_styled_toml(data)

        assert "domain" in result
        assert "[concept]" in result
        assert "TestConcept" in result

    def test_pipe_compose_construct_serialization_format(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test PipeComposeBlueprint construct serializes to correct MTHDS format."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        blueprint = PipelexBundleBlueprint(
            domain="test_domain",
            pipe={
                "compose_test": PipeComposeBlueprint.model_validate(
                    {
                        "description": "Test compose",
                        "inputs": {"data": "Text", "info": "Text"},
                        "output": "JSON",
                        "construct": {
                            "value": {"from": "data.field"},
                            "name": {"from": "info.name"},
                        },
                    }
                )
            },
        )

        mthds_content = MthdsFactory.make_mthds_content(blueprint=blueprint)

        # Should have nested table section, not inline
        assert "[pipe.compose_test.construct]" in mthds_content
        # Should use concise format { from = '...' }
        assert "value = { from = 'data.field' }" in mthds_content
        assert "name = { from = 'info.name' }" in mthds_content
        # Should NOT have internal field names
        assert "construct_blueprint" not in mthds_content
        assert "fields" not in mthds_content
        assert "from_path" not in mthds_content
        assert "method" not in mthds_content

    def test_pipe_compose_construct_fixed_and_template_serialization(self, mocker: MockerFixture, mock_mthds_config: MthdsConfig):
        """Test PipeComposeBlueprint construct with FIXED and TEMPLATE methods serializes correctly."""
        _mock_config = mocker.patch.object(MthdsFactory, "_mthds_config", return_value=mock_mthds_config)

        blueprint = PipelexBundleBlueprint(
            domain="test_domain",
            pipe={
                "compose_mixed": PipeComposeBlueprint.model_validate(
                    {
                        "description": "Mixed construct methods",
                        "inputs": {"data": "Text"},
                        "output": "JSON",
                        "construct": {
                            "fixed_string": "hello world",
                            "fixed_number": 42,
                            "from_var": {"from": "data.value"},
                            "templated": {"template": "Hello {{ data.name }}!"},
                        },
                    }
                )
            },
        )

        mthds_content = MthdsFactory.make_mthds_content(blueprint=blueprint)

        # Should have nested table section
        assert "[pipe.compose_mixed.construct]" in mthds_content
        # Fixed values should appear directly
        assert "fixed_string = 'hello world'" in mthds_content
        assert "fixed_number = 42" in mthds_content
        # From var should use { from = '...' }
        assert "from_var = { from = 'data.value' }" in mthds_content
        # Template should use { template = '...' }
        assert "templated = { template = 'Hello {{ data.name }}!' }" in mthds_content
        # Should NOT have internal field names (as key names in construct)
        assert "fixed_value" not in mthds_content
        assert "from_path" not in mthds_content
        # Check that 'method' does not appear as a key in construct section
        assert "method =" not in mthds_content
