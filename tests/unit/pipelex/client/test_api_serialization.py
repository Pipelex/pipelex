import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

# Import additional types for complex testing
from typing import Any, Dict, List, Optional, cast

import pytest
from pydantic import BaseModel

from pipelex.client.api_serializer import ApiSerializationError, ApiSerializer
from pipelex.client.protocol import COMPACT_MEMORY_KEY
from pipelex.core.concept_native import NativeConcept
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.stuff_content import NumberContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from tests.test_pipelines.datetime import DateTimeEvent


# Test models for complex scenarios
class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(BaseModel):
    is_complete: bool
    completion_date: Optional[datetime] = None
    notes: List[str] = []


class ComplexTask(BaseModel):
    task_id: str
    title: str
    priority: Priority
    status: TaskStatus
    due_dates: List[datetime]
    metadata: Dict[str, Any]
    score: Optional[Decimal] = None


class Project(BaseModel):
    name: str
    created_at: datetime
    tasks: List[ComplexTask]
    settings: Dict[str, Any]


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
        compact_memory = ApiSerializer.serialize_working_memory_for_api(datetime_content_memory)

        # Should have one entry for the datetime content
        assert len(compact_memory) == 1
        assert "project_meeting" in compact_memory

        # Check the dict structure
        datetime_blueprint = compact_memory["project_meeting"]
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
        compact_memory = ApiSerializer.serialize_working_memory_for_api(datetime_content_memory)

        # This should NOT raise an exception now
        json_string = json.dumps(compact_memory)
        roundtrip = json.loads(json_string)

        # Verify roundtrip works
        assert roundtrip == compact_memory

        # Verify datetime fields are strings
        content = roundtrip["project_meeting"]["content"]
        assert isinstance(content["start_time"], str)
        assert isinstance(content["end_time"], str)
        assert isinstance(content["created_at"], str)

    def test_serialize_text_content(self, text_content_memory: WorkingMemory):
        """Test that text content is handled specially."""
        compact_memory = ApiSerializer.serialize_working_memory_for_api(text_content_memory)

        assert len(compact_memory) == 1
        assert "sample_text" in compact_memory

        text_blueprint = compact_memory["sample_text"]
        assert text_blueprint["concept_code"] == NativeConcept.TEXT.code
        assert isinstance(text_blueprint["content"], str)
        assert text_blueprint["content"] == "Sample text content"

    def test_serialize_number_content(self, number_content_memory: WorkingMemory):
        """Test that number content is properly serialized."""
        compact_memory = ApiSerializer.serialize_working_memory_for_api(number_content_memory)

        assert len(compact_memory) == 1
        assert "pi_value" in compact_memory

        number_blueprint = compact_memory["pi_value"]
        assert number_blueprint["concept_code"] == "native.Number"
        assert isinstance(number_blueprint["content"], dict)
        assert number_blueprint["content"]["number"] == 3.14159

    def test_serialize_pipe_output(self, datetime_content_memory: WorkingMemory):
        """Test that PipeOutput is properly serialized."""
        pipe_output = PipeOutput(working_memory=datetime_content_memory)
        reduced_output = ApiSerializer.serialize_pipe_output_for_api(pipe_output)

        assert COMPACT_MEMORY_KEY in reduced_output

        # Should contain the same structure as working memory serialization
        working_memory_data = reduced_output[COMPACT_MEMORY_KEY]
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

    # ===== COMPLEX TESTS =====

    def test_serialize_complex_nested_pydantic_models(self):
        """Test serialization with deeply nested Pydantic models."""
        # Create complex nested structure
        task1 = ComplexTask(
            task_id="TASK-001",
            title="Implement Feature X",
            priority=Priority.HIGH,
            status=TaskStatus(is_complete=False, completion_date=None, notes=["Started implementation", "Need to review specs"]),
            due_dates=[datetime(2024, 2, 15, 10, 0, 0), datetime(2024, 2, 28, 17, 0, 0)],
            metadata={"tags": ["frontend", "ui"], "estimated_hours": 40.5, "assigned_team": "Alpha"},
            score=Decimal("8.75"),
        )

        task2 = ComplexTask(
            task_id="TASK-002",
            title="Bug Fix",
            priority=Priority.MEDIUM,
            status=TaskStatus(is_complete=True, completion_date=datetime(2024, 1, 20, 14, 30, 0), notes=["Fixed authentication issue"]),
            due_dates=[datetime(2024, 1, 25, 12, 0, 0)],
            metadata={"severity": "medium", "component": "auth"},
            score=Decimal("6.00"),
        )

        project = Project(
            name="Q1 Development Sprint",
            created_at=datetime(2024, 1, 1, 9, 0, 0),
            tasks=[task1, task2],
            settings={"auto_assign": True, "notification_hours": [9, 14, 18], "max_parallel_tasks": 5},
        )

        # Create stuff content from the complex model - use a proper StructuredContent subclass
        from pipelex.core.stuff_content import StructuredContent

        class ProjectContent(StructuredContent):
            name: str
            created_at: datetime
            tasks: List[ComplexTask]
            settings: Dict[str, Any]

        project_content = ProjectContent(name=project.name, created_at=project.created_at, tasks=project.tasks, settings=project.settings)

        stuff = StuffFactory.make_stuff(concept_str="project.Complex", name="complex_project", content=project_content)
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Test serialization
        compact_memory = ApiSerializer.serialize_working_memory_for_api(memory)

        # Verify JSON serializable - this is the key test!
        json_string = json.dumps(compact_memory)
        roundtrip = json.loads(json_string)
        assert roundtrip == compact_memory

        # Verify complex structure is preserved
        content = compact_memory["complex_project"]["content"]
        assert content["name"] == "Q1 Development Sprint"
        assert len(content["tasks"]) == 2

        # Verify nested datetime formatting
        assert content["created_at"] == "2024-01-01T09:00:00"
        assert content["tasks"][0]["due_dates"][0] == "2024-02-15T10:00:00"
        assert content["tasks"][1]["status"]["completion_date"] == "2024-01-20T14:30:00"

        # Verify enums are converted to values
        assert content["tasks"][0]["priority"] == "high"  # Priority.HIGH.value
        assert content["tasks"][1]["priority"] == "medium"  # Priority.MEDIUM.value

        # Verify Decimal handling (converted to float)
        assert content["tasks"][0]["score"] == 8.75  # float(Decimal("8.75"))
        assert content["tasks"][1]["score"] == 6.0  # float(Decimal("6.00"))

    def test_serialize_lists_of_datetimes(self):
        """Test serialization of lists containing datetime objects."""
        from pipelex.core.stuff_content import StructuredContent

        class ScheduleContent(StructuredContent):
            meeting_times: List[datetime]
            deadlines: Dict[str, datetime]

        schedule = ScheduleContent(
            meeting_times=[datetime(2024, 1, 15, 10, 0, 0), datetime(2024, 1, 16, 14, 30, 0), datetime(2024, 1, 17, 9, 15, 0)],
            deadlines={"milestone_1": datetime(2024, 2, 1, 23, 59, 59), "milestone_2": datetime(2024, 3, 15, 17, 0, 0)},
        )

        stuff = StuffFactory.make_stuff(concept_str="schedule.Complex", name="schedule", content=schedule)
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        compact_memory = ApiSerializer.serialize_working_memory_for_api(memory)

        # Verify JSON serializable
        json_string = json.dumps(compact_memory)
        roundtrip = json.loads(json_string)
        assert roundtrip == compact_memory

        content = compact_memory["schedule"]["content"]

        # Verify list of datetimes
        assert len(content["meeting_times"]) == 3
        assert content["meeting_times"][0] == "2024-01-15T10:00:00"
        assert content["meeting_times"][1] == "2024-01-16T14:30:00"
        assert content["meeting_times"][2] == "2024-01-17T09:15:00"

        # Verify dict of datetimes
        assert content["deadlines"]["milestone_1"] == "2024-02-01T23:59:59"
        assert content["deadlines"]["milestone_2"] == "2024-03-15T17:00:00"

    def test_serialize_with_none_values(self):
        """Test serialization with None/Optional values."""
        from pipelex.core.stuff_content import StructuredContent

        class OptionalContent(StructuredContent):
            required_field: str
            optional_datetime: Optional[datetime]
            optional_list: Optional[List[str]]
            nullable_dict: Optional[Dict[str, Any]]

        content = OptionalContent(required_field="test", optional_datetime=None, optional_list=None, nullable_dict=None)

        stuff = StuffFactory.make_stuff(concept_str="optional.Test", name="optional_test", content=content)
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        compact_memory = ApiSerializer.serialize_working_memory_for_api(memory)

        # Verify JSON serializable
        json_string = json.dumps(compact_memory)
        roundtrip = json.loads(json_string)
        assert roundtrip == compact_memory

        content_data = compact_memory["optional_test"]["content"]
        assert content_data["required_field"] == "test"
        assert content_data["optional_datetime"] is None
        assert content_data["optional_list"] is None
        assert content_data["nullable_dict"] is None

    def test_serialize_deeply_nested_structure(self):
        """Test serialization with deeply nested data structures."""
        from pipelex.core.stuff_content import StructuredContent

        class DeepContent(StructuredContent):
            level1: Dict[str, Any]

        deep_structure = {
            "level2": {
                "level3": {
                    "level4": {
                        "timestamps": [datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 2, 13, 30, 0)],
                        "metadata": {"created": datetime(2024, 1, 1, 10, 0, 0), "modified": datetime(2024, 1, 3, 15, 45, 0)},
                    }
                }
            }
        }

        content = DeepContent(level1=deep_structure)

        stuff = StuffFactory.make_stuff(concept_str="deep.Nested", name="deep_test", content=content)
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        compact_memory = ApiSerializer.serialize_working_memory_for_api(memory)

        # Verify JSON serializable
        json_string = json.dumps(compact_memory)
        roundtrip = json.loads(json_string)
        assert roundtrip == compact_memory

        # Navigate to deep nested datetime
        content_data = compact_memory["deep_test"]["content"]
        level4 = content_data["level1"]["level2"]["level3"]["level4"]

        # Verify deep datetime formatting
        assert level4["timestamps"][0] == "2024-01-01T12:00:00"
        assert level4["timestamps"][1] == "2024-01-02T13:30:00"
        assert level4["metadata"]["created"] == "2024-01-01T10:00:00"
        assert level4["metadata"]["modified"] == "2024-01-03T15:45:00"

    def test_serialize_with_class_module_fields_removal(self):
        """Test that __class__ and __module__ fields are properly removed."""
        from pipelex.core.stuff_content import StructuredContent

        class TestContent(StructuredContent):
            data: Dict[str, Any]

        # Create content with intentional __class__ and __module__ fields
        test_data = {
            "normal_field": "value",
            "__class__": "ShouldBeRemoved",
            "__module__": "should.be.removed",
            "nested": {"field": "nested_value", "__class__": "NestedShouldBeRemoved", "__module__": "nested.should.be.removed"},
            "list_with_class": [{"item": "value1", "__class__": "ItemClass"}, {"item": "value2", "__module__": "item.module"}],
        }

        content = TestContent(data=test_data)

        stuff = StuffFactory.make_stuff(concept_str="test.ClassModule", name="class_test", content=content)
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        compact_memory = ApiSerializer.serialize_working_memory_for_api(memory)

        content_data = compact_memory["class_test"]["content"]

        # Verify top-level __class__ and __module__ removal
        assert "__class__" not in content_data
        assert "__module__" not in content_data
        assert content_data["data"]["normal_field"] == "value"

        # Verify nested __class__ and __module__ removal
        assert "__class__" not in content_data["data"]
        assert "__module__" not in content_data["data"]
        assert "__class__" not in content_data["data"]["nested"]
        assert "__module__" not in content_data["data"]["nested"]
        assert content_data["data"]["nested"]["field"] == "nested_value"

        # Verify list item __class__ and __module__ removal
        assert "__class__" not in content_data["data"]["list_with_class"][0]
        assert "__module__" not in content_data["data"]["list_with_class"][1]
        assert content_data["data"]["list_with_class"][0]["item"] == "value1"
        assert content_data["data"]["list_with_class"][1]["item"] == "value2"

    def test_serialize_with_path_objects(self):
        """Test serialization with pathlib.Path objects."""
        from pipelex.core.stuff_content import StructuredContent

        class PathContent(StructuredContent):
            file_path: Path
            directory_path: Path
            nested_paths: Dict[str, Path]
            path_list: List[Path]

        content = PathContent(
            file_path=Path("/home/user/documents/file.txt"),
            directory_path=Path("/var/log/"),
            nested_paths={"config": Path("/etc/config.yaml"), "temp": Path("/tmp/temp.log")},
            path_list=[Path("/usr/bin/python"), Path("/opt/app/main.py")],
        )

        stuff = StuffFactory.make_stuff(concept_str="path.Test", name="path_test", content=content)
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        compact_memory = ApiSerializer.serialize_working_memory_for_api(memory)

        # Verify JSON serializable - this is the key test!
        json_string = json.dumps(compact_memory)
        roundtrip = json.loads(json_string)
        assert roundtrip == compact_memory

        # Verify Path objects were converted to strings
        content_data = compact_memory["path_test"]["content"]

        # Check that paths are now strings
        assert content_data["file_path"] == "/home/user/documents/file.txt"
        assert content_data["directory_path"] == "/var/log"

        # Verify nested paths in dict
        assert content_data["nested_paths"]["config"] == "/etc/config.yaml"
        assert content_data["nested_paths"]["temp"] == "/tmp/temp.log"

        # Verify paths in list
        assert content_data["path_list"][0] == "/usr/bin/python"
        assert content_data["path_list"][1] == "/opt/app/main.py"
