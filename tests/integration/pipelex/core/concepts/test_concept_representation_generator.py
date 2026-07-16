"""Integration tests for ConceptRepresentationGenerator with complex nested structures."""

from pydantic import Field

from pipelex.core.concepts.concept_representation_generator import (
    ConceptRepresentationFormat,
    ConceptRepresentationGenerator,
    generate_json_representation,
    generate_python_representation,
)
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

# =============================================================================
# Complex nested structures for integration testing
# =============================================================================


class Attachment(StructuredContent):
    """Represents a message attachment."""

    name: str = Field(..., description="Name of the attachment file")
    url: str = Field(..., description="URL of the attachment")


class Embed(StructuredContent):
    """Represents a message embed."""

    title: str = Field(..., description="Title of the embed")
    description: str = Field(..., description="Description of the embed content")
    embed_type: str = Field(..., description="Type of the embed")


class Message(StructuredContent):
    """Represents a message with nested attachments and embeds."""

    author: str = Field(..., description="Author of the message")
    content: str = Field(..., description="Content of the message")
    attachments: list[Attachment] = Field(default_factory=empty_list_factory_of(Attachment), description="List of attachments")
    embeds: list[Embed] = Field(default_factory=empty_list_factory_of(Embed), description="List of embeds")
    link: str = Field(..., description="Link to the message")


class Channel(StructuredContent):
    """Represents a channel with messages."""

    name: str = Field(..., description="Name of the channel")
    position: int = Field(..., description="Position of the channel")
    messages: list[Message] = Field(default_factory=empty_list_factory_of(Message), description="List of messages")


class ChannelSummary(StructuredContent):
    """Represents a summarized channel."""

    channel_name: str = Field(..., description="Name of the channel")
    summary_items: list[str] = Field(..., description="Summaries of the channel's activity")


class Newsletter(StructuredContent):
    """Represents a newsletter with multiple sections."""

    weekly_summary: str = Field(..., description="Summary of weekly content")
    new_members: list[str] = Field(default_factory=list, description="New member introductions")
    channel_sections: list[ChannelSummary] = Field(default_factory=empty_list_factory_of(ChannelSummary), description="Channel summaries")


# =============================================================================
# Integration tests with exact expected results
# =============================================================================


class TestComplexNestedStructuresJson:
    """Integration tests for complex nested structures with JSON output."""

    def test_attachment_json(self) -> None:
        """Test simple Attachment generates correct JSON."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Attachment", structure_class=Attachment)
        assert result["concept"] == "test.Attachment"
        assert result["content"]["name"] == "name_value"
        assert result["content"]["url"].startswith("https://mock.invalid/")

    def test_embed_json(self) -> None:
        """Test Embed with multiple string fields generates correct JSON."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Embed", structure_class=Embed)
        expected = {
            "concept": "test.Embed",
            "content": {
                "title": "title_value",
                "description": "description_value",
                "embed_type": "embed_type_value",
            },
        }
        assert result == expected

    def test_message_json_recursive(self) -> None:
        """Test Message with nested Attachment and Embed lists generates correct recursive JSON."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Message", structure_class=Message)
        content = result["content"]
        assert content["author"] == "author_value"
        assert content["content"] == "content_value"
        assert content["link"] == "link_value"
        assert len(content["attachments"]) == 1
        assert content["attachments"][0]["name"] == "name_value"
        assert content["attachments"][0]["url"].startswith("https://mock.invalid/")
        assert content["embeds"] == [{"title": "title_value", "description": "description_value", "embed_type": "embed_type_value"}]

    def test_channel_json_deeply_nested(self) -> None:
        """Test Channel with deeply nested messages generates correct JSON."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Channel", structure_class=Channel)
        content = result["content"]
        assert content["name"] == "name_value"
        assert content["position"] == 0
        assert len(content["messages"]) == 1
        message = content["messages"][0]
        assert message["author"] == "author_value"
        assert len(message["attachments"]) == 1
        assert message["attachments"][0]["url"].startswith("https://mock.invalid/")

    def test_newsletter_json_multiple_lists(self) -> None:
        """Test Newsletter with multiple list fields generates correct JSON."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Newsletter", structure_class=Newsletter)
        expected = {
            "concept": "test.Newsletter",
            "content": {
                "weekly_summary": "weekly_summary_value",
                "new_members": ["new_members_item_value"],
                "channel_sections": [
                    {
                        "channel_name": "channel_name_value",
                        "summary_items": ["summary_items_item_value"],
                    }
                ],
            },
        }
        assert result == expected


class TestComplexNestedStructuresPython:
    """Integration tests for complex nested structures with Python output."""

    def test_attachment_python(self) -> None:
        """Test simple Attachment generates correct Python instantiation."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_representation("test.Attachment", structure_class=Attachment)
        assert result["concept"] == "test.Attachment"
        assert 'Attachment(name="name_value", url="https://mock.invalid/' in result["content"]

    def test_message_python_recursive(self) -> None:
        """Test Message with nested structures generates correct Python."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_representation("test.Message", structure_class=Message)
        content = result["content"]
        assert content.startswith(
            'Message(author="author_value", content="content_value", attachments=[Attachment(name="name_value", url="https://mock.invalid/'
        )
        assert 'embeds=[Embed(title="title_value"' in content
        assert 'link="link_value")' in content

    def test_channel_python_deeply_nested(self) -> None:
        """Test Channel with deeply nested structures generates correct Python."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_representation("test.Channel", structure_class=Channel)
        content = result["content"]
        assert content.startswith('Channel(name="name_value", position=0, messages=[Message(')
        assert 'Attachment(name="name_value", url="https://mock.invalid/' in content


class TestImportsTrackingIntegration:
    """Integration tests for import tracking with complex structures."""

    def test_channel_tracks_all_nested_imports(self) -> None:
        """Test that Channel tracks imports for all nested classes."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Channel", structure_class=Channel)

        expected_imports = {"Channel", "Message", "Attachment", "Embed"}
        assert generator.imports_needed == expected_imports

    def test_newsletter_tracks_all_imports(self) -> None:
        """Test that Newsletter tracks imports for all nested classes."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Newsletter", structure_class=Newsletter)

        expected_imports = {"Newsletter", "ChannelSummary"}
        assert generator.imports_needed == expected_imports


class TestConvenienceFunctionsIntegration:
    """Integration tests for convenience functions with complex structures."""

    def test_generate_json_representation_complex(self) -> None:
        """Test generate_json_representation with complex structure."""
        result = generate_json_representation("test.Message", structure_class=Message)
        assert result["concept"] == "test.Message"
        assert "attachments" in result["content"]
        assert len(result["content"]["attachments"]) == 1
        assert result["content"]["attachments"][0]["name"] == "name_value"
        assert result["content"]["attachments"][0]["url"].startswith("https://mock.invalid/")

    def test_generate_python_representation_complex(self) -> None:
        """Test generate_python_representation with complex structure."""
        result, imports = generate_python_representation("test.Message", structure_class=Message)
        assert result["concept"] == "test.Message"
        assert "Message(" in result["content"]
        assert "Attachment(" in result["content"]
        assert "Message" in imports
        assert "Attachment" in imports
        assert "Embed" in imports
