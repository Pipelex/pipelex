"""Unit tests for string escaping in StructureGenerator.

This module tests that field descriptions and default values containing special
characters (quotes, backslashes, newlines, etc.) are properly escaped in the
generated Python code.
"""

import ast

from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generator import StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent


class TestStructureGeneratorEscaping:
    """Test string escaping in structure generation."""

    def test_escape_double_quotes_in_description(self):
        """Test that double quotes in field descriptions are properly escaped."""
        # This is the user's reported bug case
        description = 'The species or type of animal (e.g., "fox", "penguin", "octopus")'

        blueprint = {
            "animal_type": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("Animal", blueprint)

        # Verify the code compiles without SyntaxError
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify the generated class can be instantiated
        assert issubclass(generated_class, StructuredContent)
        instance = generated_class(animal_type="fox")  # pyright: ignore[reportCallIssue]
        assert instance.animal_type == "fox"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        # Verify the description in the generated code matches
        # The description should be preserved in Field(description=...)
        assert "animal_type" in generated_code
        assert "description=" in generated_code

    def test_escape_single_quotes_in_description(self):
        """Test that single quotes in field descriptions are properly escaped."""
        description = "This is John's description with a single quote"

        blueprint = {
            "field_name": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("TestClass", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(field_name="test")  # pyright: ignore[reportCallIssue]
        assert instance.field_name == "test"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_mixed_quotes_in_description(self):
        """Test that mixed single and double quotes are properly escaped."""
        description = """He said "it's working!" with excitement"""

        blueprint = {
            "message": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("Message", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(message="Hello world")  # pyright: ignore[reportCallIssue]
        assert instance.message == "Hello world"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_backslashes_in_description(self):
        """Test that backslashes in field descriptions are properly escaped."""
        description = r"Path separator: C:\Users\Documents\file.txt"

        blueprint = {
            "path": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("FilePath", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(path="/usr/local/bin")  # pyright: ignore[reportCallIssue]
        assert instance.path == "/usr/local/bin"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_newlines_in_description(self):
        """Test that newlines in field descriptions are properly escaped."""
        description = "Line 1\nLine 2\nLine 3"

        blueprint = {
            "multiline": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("MultiLine", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(multiline="test")  # pyright: ignore[reportCallIssue]
        assert instance.multiline == "test"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_tabs_in_description(self):
        """Test that tabs in field descriptions are properly escaped."""
        description = "Column1\tColumn2\tColumn3"

        blueprint = {
            "columns": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("Columns", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(columns="A,B,C")  # pyright: ignore[reportCallIssue]
        assert instance.columns == "A,B,C"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_multiple_special_characters_combined(self):
        """Test combination of multiple special characters."""
        description = r"""Complex: "quoted", 'single', backslash\, tab	, newline
and more!"""

        blueprint = {
            "complex_field": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("ComplexType", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(complex_field="value")  # pyright: ignore[reportCallIssue]
        assert instance.complex_field == "value"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_default_value_with_quotes(self):
        """Test that default values with quotes are properly escaped."""
        default_value = 'Example: "quoted text"'

        blueprint = {
            "field_with_default": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="A field with quoted default",
                required=False,
                default_value=default_value,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("WithDefault", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works with default
        instance = generated_class()  # pyright: ignore[reportCallIssue]
        assert instance.field_with_default == default_value  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        # Verify instantiation works with explicit value
        instance2 = generated_class(field_with_default="custom")  # pyright: ignore[reportCallIssue]
        assert instance2.field_with_default == "custom"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_escape_default_value_with_backslashes(self):
        """Test that default values with backslashes are properly escaped."""
        default_value = r"C:\Program Files\App"

        blueprint = {
            "path": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="Default path",
                required=False,
                default_value=default_value,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("DefaultPath", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works with default
        instance = generated_class()  # pyright: ignore[reportCallIssue]
        assert instance.path == default_value  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_empty_string_description(self):
        """Test that empty string descriptions are handled correctly."""
        description = ""

        blueprint = {
            "empty_desc": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("EmptyDesc", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(empty_desc="value")  # pyright: ignore[reportCallIssue]
        assert instance.empty_desc == "value"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_very_long_description_with_quotes(self):
        """Test that very long descriptions with quotes are handled correctly."""
        description = (
            "This is a very long description that contains many words and also has "
            'some "quoted sections" that need to be properly escaped. It goes on and on '
            "with more details about the field, including examples like "
            '"example1", "example2", and "example3". The description continues with '
            "even more information to test the robustness of the escaping mechanism."
        )

        blueprint = {
            "long_field": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("LongDesc", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(long_field="test")  # pyright: ignore[reportCallIssue]
        assert instance.long_field == "test"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_unicode_characters_in_description(self):
        """Test that unicode characters in descriptions are handled correctly."""
        description = "Unicode characters: café, naïve, 日本語, emoji 🎉"

        blueprint = {
            "unicode_field": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("UnicodeTest", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(unicode_field="test")  # pyright: ignore[reportCallIssue]
        assert instance.unicode_field == "test"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_carriage_return_in_description(self):
        """Test that carriage returns in descriptions are handled correctly."""
        description = "Line 1\r\nLine 2\r\nLine 3"

        blueprint = {
            "crlf_field": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=description,
                required=True,
            )
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("CRLF", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works
        instance = generated_class(crlf_field="test")  # pyright: ignore[reportCallIssue]
        assert instance.crlf_field == "test"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_multiple_fields_with_various_escaping_needs(self):
        """Test a realistic scenario with multiple fields needing different escaping."""
        blueprint = {
            "animal_type": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description='The species or type of animal (e.g., "fox", "penguin", "octopus")',
                required=True,
            ),
            "owner_name": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="The owner's full name",
                required=False,
            ),
            "file_path": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description=r"Location on disk (e.g., C:\Animals\data.txt)",
                required=False,
                default_value=r"C:\default\path",
            ),
            "notes": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description='Notes with "quotes" and\nnewlines',
                required=False,
            ),
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("AnimalRecord", blueprint)

        # Verify the code compiles
        ast.parse(generated_code)
        compile(generated_code, "<generated>", "exec")

        # Verify instantiation works with all fields
        instance = generated_class(  # pyright: ignore[reportCallIssue]
            animal_type="dog",
            owner_name="John Smith",
            file_path=r"C:\custom\location",
            notes="Some notes here",
        )
        assert instance.animal_type == "dog"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        assert instance.owner_name == "John Smith"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        assert instance.file_path == r"C:\custom\location"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        assert instance.notes == "Some notes here"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        # Verify instantiation with only required fields
        instance2 = generated_class(animal_type="cat")  # pyright: ignore[reportCallIssue]
        assert instance2.animal_type == "cat"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        assert instance2.file_path == r"C:\default\path"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
