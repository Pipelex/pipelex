import json
from datetime import datetime
from typing import cast

import pytest

from pipelex.client.factory import ApiSerializationError, ApiSerializer
from pipelex.core.concept_native import NativeConcept
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.stuff_content import NumberContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from tests.test_pipelines.datetime import DateTimeEvent


class TestApiSerialization:
    """Test API-specific serialization with kajson, datetime formatting, and cleanup."""

    @pytest.fixture
    def datetime_content_memory(self) -> WorkingMemory:
        """Create WorkingMemory with datetime content."""
        datetime_event = DateTimeEvent(
            event_name="Project Kickoff Meeting",
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            end_time=datetime(2024, 1, 15, 11, 30, 0),
            created_at=datetime(2024, 1, 1, 9, 0, 0),
        )

        stuff = StuffFactory.make_stuff(concept_str="event.DateTimeEvent", name="project_meeting", content=datetime_event)
        return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

    @pytest.fixture
    def text_content_memory(self) -> WorkingMemory:
        """Create WorkingMemory with text content."""
        return WorkingMemoryFactory.make_from_text(text="Sample text content", concept_str=NativeConcept.TEXT.code, name="sample_text")

    @pytest.fixture
    def number_content_memory(self) -> WorkingMemory:
        """Create WorkingMemory with number content."""
        number_content = NumberContent(number=3.14159)
        stuff = StuffFactory.make_stuff(concept_str="native.Number", name="pi_value", content=number_content)
        return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

    def test_serialize_working_memory_with_datetime(self, datetime_content_memory: WorkingMemory):
        """Test that datetime content is properly serialized to ISO format strings."""
        reduced_memory = ApiSerializer.serialize_working_memory_for_api(datetime_content_memory)

        from pipelex import pretty_print

        pretty_print(reduced_memory, title="API Serialized Memory")

        # Should have one entry for the datetime content
        assert len(reduced_memory) == 1
        assert "project_meeting" in reduced_memory

        # Check the dict structure
        datetime_blueprint = reduced_memory["project_meeting"]
        assert isinstance(datetime_blueprint, dict)
        assert datetime_blueprint["concept_code"] == "event.DateTimeEvent"

        # Check content is properly serialized
        content = datetime_blueprint["content"]
        assert isinstance(content, dict)
        assert "event_name" in content
        assert "start_time" in content
        assert "end_time" in content
        assert "created_at" in content

        # Verify the event name
        assert content["event_name"] == "Project Kickoff Meeting"

        # Verify datetime objects are now formatted as ISO strings
        assert content["start_time"] == "2024-01-15T10:00:00"
        assert content["end_time"] == "2024-01-15T11:30:00"
        assert content["created_at"] == "2024-01-01T09:00:00"

        # Ensure no __module__ or __class__ fields are present
        assert "__module__" not in content
        assert "__class__" not in content

    def test_api_serialized_memory_is_json_serializable(self, datetime_content_memory: WorkingMemory):
        """Test that API serialized memory is JSON serializable."""
        reduced_memory = ApiSerializer.serialize_working_memory_for_api(datetime_content_memory)

        # This should NOT raise an exception now
        json_string = json.dumps(reduced_memory)
        roundtrip = json.loads(json_string)

        # Verify roundtrip works
        assert roundtrip == reduced_memory

        # Verify datetime fields are strings
        content = roundtrip["project_meeting"]["content"]
        assert isinstance(content["start_time"], str)
        assert isinstance(content["end_time"], str)
        assert isinstance(content["created_at"], str)

    def test_serialize_text_content(self, text_content_memory: WorkingMemory):
        """Test that text content is handled specially."""
        reduced_memory = ApiSerializer.serialize_working_memory_for_api(text_content_memory)

        assert len(reduced_memory) == 1
        assert "sample_text" in reduced_memory

        text_blueprint = reduced_memory["sample_text"]
        assert text_blueprint["concept_code"] == NativeConcept.TEXT.code
        assert isinstance(text_blueprint["content"], str)
        assert text_blueprint["content"] == "Sample text content"

    def test_serialize_number_content(self, number_content_memory: WorkingMemory):
        """Test that number content is properly serialized."""
        reduced_memory = ApiSerializer.serialize_working_memory_for_api(number_content_memory)

        assert len(reduced_memory) == 1
        assert "pi_value" in reduced_memory

        number_blueprint = reduced_memory["pi_value"]
        assert number_blueprint["concept_code"] == "native.Number"
        assert isinstance(number_blueprint["content"], dict)
        assert number_blueprint["content"]["number"] == 3.14159

    def test_serialize_pipe_output(self, datetime_content_memory: WorkingMemory):
        """Test that PipeOutput is properly serialized."""
        pipe_output = PipeOutput(working_memory=datetime_content_memory)
        reduced_output = ApiSerializer.serialize_pipe_output_for_api(pipe_output)

        assert "working_memory" in reduced_output

        # Should contain the same structure as working memory serialization
        working_memory_data = reduced_output["working_memory"]
        assert "project_meeting" in working_memory_data

        # Verify datetime formatting
        content = working_memory_data["project_meeting"]["content"]
        assert content["start_time"] == "2024-01-15T10:00:00"

    def test_make_stuff_content_from_api_data_text(self):
        """Test creating StuffContent from API data for text."""
        content = ApiSerializer.make_stuff_content_from_api_data(concept_code=NativeConcept.TEXT.code, value="Test text content")

        assert isinstance(content, TextContent)
        assert content.text == "Test text content"

    def test_make_stuff_content_from_api_data_datetime(self):
        """Test creating StuffContent from API datetime data."""
        api_data = {
            "event_name": "Test Event",
            "start_time": "2024-01-15T10:00:00",
            "end_time": "2024-01-15T11:30:00",
            "created_at": "2024-01-01T09:00:00",
        }

        content = ApiSerializer.make_stuff_content_from_api_data(concept_code="event.DateTimeEvent", value=api_data)
        content = cast(DateTimeEvent, content)
        assert content.event_name == "Test Event"
        assert content.start_time == datetime(2024, 1, 15, 10, 0, 0)
        assert content.end_time == datetime(2024, 1, 15, 11, 30, 0)
        assert content.created_at == datetime(2024, 1, 1, 9, 0, 0)

    def test_make_stuff_content_from_api_data_error(self):
        """Test error handling for invalid concept codes."""
        with pytest.raises(ApiSerializationError, match="Failed to create StuffContent"):
            ApiSerializer.make_stuff_content_from_api_data(concept_code="invalid.ConceptCode", value={"some": "data"})

    def test_make_stuff_content_from_api_data_text_concept_no_structure(self):
        """Test creating StuffContent from API data for concept with no structure (should be TextContent)."""
        # Test case for concept that has no structure - should be treated as TextContent
        content = ApiSerializer.make_stuff_content_from_api_data(concept_code="answer.Question", value="What is the capital of France?")

        assert isinstance(content, TextContent)
        assert content.text == "What is the capital of France?"

    def test_make_stuff_content_from_api_data_various_cases(self):
        """Test make_stuff_content_from_api_data with various input cases."""

        # Test 1: Native text concept
        text_content = ApiSerializer.make_stuff_content_from_api_data(concept_code=NativeConcept.TEXT.code, value="Simple text")
        assert isinstance(text_content, TextContent)
        assert text_content.text == "Simple text"

        # Test 2: Concept with no structure should become TextContent
        question_content = ApiSerializer.make_stuff_content_from_api_data(concept_code="answer.Question", value="What is 2+2?")
        assert isinstance(question_content, TextContent)
        assert question_content.text == "What is 2+2?"

        # Test 3: Number content (structured)
        number_data = {"number": 42.0}
        number_content = ApiSerializer.make_stuff_content_from_api_data(concept_code="native.Number", value=number_data)
        assert number_content.__class__.__name__ == "NumberContent"
        assert hasattr(number_content, "number")
        assert number_content.number == 42.0  # type: ignore

    def test_datetime_format_consistency(self):
        """Test that the datetime format is consistent."""
        test_datetime = datetime(2024, 12, 25, 15, 30, 45)
        formatted = test_datetime.strftime(ApiSerializer.API_DATETIME_FORMAT)

        assert formatted == "2024-12-25T15:30:45"

        # Verify no microseconds or timezone info
        assert "." not in formatted
        assert "+" not in formatted
        assert "Z" not in formatted
