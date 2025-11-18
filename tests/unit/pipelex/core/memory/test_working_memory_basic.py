from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.memory.conftest import TestWorkingMemoryData


class TestWorkingMemoryBasic:
    """Unit tests for WorkingMemory basic functionality."""

    def test_working_memory_basic_functionality(self, single_text_memory: WorkingMemory):
        """Test basic WorkingMemory functionality."""
        # Should have one entry for the text content
        assert len(single_text_memory.root) == 1
        assert "sample_text" in single_text_memory.root

        # Check stuff retrieval
        stuff = single_text_memory.get_stuff("sample_text")
        assert stuff.concept.code == NativeConceptCode.TEXT
        assert isinstance(stuff.content, TextContent)
        assert stuff.content.text == TestWorkingMemoryData.SAMPLE_TEXT

    def test_working_memory_aliases(self, memory_with_aliases: WorkingMemory):
        """Test WorkingMemory with aliases."""
        # Should have two root items and two aliases other then the main stuff
        assert MAIN_STUFF_NAME in memory_with_aliases.aliases
        # Remove it from the aliases
        aliases = memory_with_aliases.aliases.copy()
        del aliases[MAIN_STUFF_NAME]
        assert len(memory_with_aliases.root) == 2
        assert len(aliases) == 2

        # Check aliases work
        primary_stuff = memory_with_aliases.get_stuff("primary_text")
        alias_stuff = memory_with_aliases.get_stuff("main_text")
        assert primary_stuff == alias_stuff

    def test_working_memory_empty(self):
        """Test empty WorkingMemory."""
        empty_memory = WorkingMemoryFactory.make_empty()
        assert len(empty_memory.root) == 0
        assert len(empty_memory.aliases) == 0
