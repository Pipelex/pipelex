from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_artefact import BaseStuffArtefactField, StuffArtefact, unwrap_stuff_artefact
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from tests.cases.documents import DocumentTestCases
from tests.cases.images import ImageTestCases
from tests.unit.pipelex.core.memory.conftest import TestWorkingMemoryData


class TestWorkingMemoryGenerateContext:
    """Unit tests for WorkingMemory.generate_context() method."""

    def test_generate_context_empty(self):
        """Test generate_context with empty WorkingMemory."""
        empty_memory = WorkingMemoryFactory.make_empty()
        context = empty_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 0

    def test_generate_context_single_text(self, single_text_memory: WorkingMemory):
        """Test generate_context with single text content."""
        context = single_text_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # sample_text + MAIN_STUFF_NAME alias
        assert "sample_text" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["sample_text"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact
        content = unwrap_stuff_artefact(artefact=artefact).content
        assert isinstance(content, TextContent)

        # Verify actual content value
        assert content.text == TestWorkingMemoryData.SAMPLE_TEXT

        # Verify MAIN_STUFF_NAME points to the same artefact
        assert context[MAIN_STUFF_NAME] is context["sample_text"]

    def test_generate_context_single_document(self, single_document_memory: WorkingMemory):
        """Test generate_context with single document content."""
        context = single_document_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # document_file + MAIN_STUFF_NAME alias
        assert "document_file" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["document_file"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact

        # Verify actual content value
        assert unwrap_stuff_artefact(artefact=artefact).as_document.url == DocumentTestCases.PDF_FILE_URL_1

        # Verify MAIN_STUFF_NAME points to the same artefact
        assert context[MAIN_STUFF_NAME] is context["document_file"]

    def test_generate_context_single_image(self, single_image_memory: WorkingMemory):
        """Test generate_context with single image content."""
        context = single_image_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # sample_image + MAIN_STUFF_NAME alias
        assert "sample_image" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["sample_image"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact
        content = unwrap_stuff_artefact(artefact=artefact).content
        assert isinstance(content, ImageContent)

        # Verify actual content value
        assert content.url == ImageTestCases.IMAGE_FILE_PATH_PNG_1

        # Verify MAIN_STUFF_NAME points to the same artefact
        assert context[MAIN_STUFF_NAME] is context["sample_image"]

    def test_generate_context_multiple_stuffs(self, multiple_stuff_memory: WorkingMemory):
        """Test generate_context with multiple stuff items."""
        context = multiple_stuff_memory.generate_context()

        assert isinstance(context, dict)
        # Should have 3 stuffs + MAIN_STUFF_NAME alias = 4 entries
        assert len(context) == 4
        assert "question" in context
        assert "document" in context
        assert "diagram" in context
        assert MAIN_STUFF_NAME in context

        # Verify each artefact is a StuffArtefact with content
        assert isinstance(context["question"], StuffArtefact)
        assert isinstance(context["document"], StuffArtefact)
        assert isinstance(context["diagram"], StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in context["question"]
        assert BaseStuffArtefactField.CONTENT_CLASS in context["document"]
        assert BaseStuffArtefactField.CONTENT_CLASS in context["diagram"]

        # Verify actual content values
        question_content = unwrap_stuff_artefact(artefact=context["question"]).content
        assert isinstance(question_content, TextContent)
        assert question_content.text == "What are the aerodynamic features?"
        document_content = unwrap_stuff_artefact(artefact=context["document"]).content
        assert isinstance(document_content, TextContent)
        assert document_content.text == TestWorkingMemoryData.SAMPLE_TEXT
        diagram_content = unwrap_stuff_artefact(artefact=context["diagram"]).content
        assert isinstance(diagram_content, ImageContent)
        assert diagram_content.url == ImageTestCases.IMAGE_FILE_PATH_PNG_1

        # Verify MAIN_STUFF_NAME points to document (main_name="document" in fixture)
        assert context[MAIN_STUFF_NAME] is context["document"]

    def test_generate_context_with_aliases(self, memory_with_aliases: WorkingMemory):
        """Test generate_context with aliases."""
        context = memory_with_aliases.generate_context()

        assert isinstance(context, dict)
        # Should have 2 stuffs + 3 aliases (MAIN_STUFF_NAME, main_text, backup_text) = 5 entries
        assert len(context) == 5
        assert "primary_text" in context
        assert "secondary_text" in context
        assert "main_text" in context
        assert "backup_text" in context
        assert MAIN_STUFF_NAME in context

        # Verify actual content values
        primary_text_content = unwrap_stuff_artefact(artefact=context["primary_text"]).content
        assert isinstance(primary_text_content, TextContent)
        assert primary_text_content.text == "Primary content"
        secondary_text_content = unwrap_stuff_artefact(artefact=context["secondary_text"]).content
        assert isinstance(secondary_text_content, TextContent)
        assert secondary_text_content.text == "Secondary content"

        # Verify aliases point to the same artefact objects (using 'is')
        assert context["main_text"] is context["primary_text"]
        assert context["backup_text"] is context["secondary_text"]
        assert context[MAIN_STUFF_NAME] is context["primary_text"]

    def test_generate_context_leaves_out_an_alias_whose_target_was_resolved_absent(self, memory_with_aliases: WorkingMemory):
        """The alias outlives its target's resolution as an absence; the context holds neither, so a template reads both as absent."""
        memory_with_aliases.record_resolved_absence(
            AbsenceRecord(variable_name="secondary_text", kind=AbsenceKind.DECLARED_ABSENT, reason="nothing to back up", producing_pipe="backup")
        )

        context = memory_with_aliases.generate_context()

        assert sorted(context) == sorted(["primary_text", "main_text", MAIN_STUFF_NAME])
        assert context["main_text"] is context["primary_text"]

    def test_generate_context_complex_list(self, complex_list_memory: WorkingMemory):
        """Test generate_context with complex list content."""
        context = complex_list_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # mixed_list + MAIN_STUFF_NAME alias
        assert "mixed_list" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["mixed_list"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact
        content = unwrap_stuff_artefact(artefact=artefact).content
        assert isinstance(content, ListContent)

        # Verify actual list content values
        list_content = unwrap_stuff_artefact(artefact=artefact).as_list_of_fixed_content_type(item_type=StuffContent)
        assert len(list_content.items) == 3
        assert isinstance(list_content.items[0], TextContent)
        assert list_content.items[0].text == "The quick brown fox jumps over the lazy dog"
        assert isinstance(list_content.items[1], ImageContent)
        assert list_content.items[1].url == ImageTestCases.IMAGE_FILE_PATH_PNG_1
        assert isinstance(list_content.items[2], NumberContent)
        assert list_content.items[2].number == 42.5

    def test_generate_context_text_and_images(self, text_and_images_memory: WorkingMemory):
        """Test generate_context with text and images content."""
        context = text_and_images_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # project_overview + MAIN_STUFF_NAME alias
        assert "project_overview" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["project_overview"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact
        content = unwrap_stuff_artefact(artefact=artefact).content
        assert isinstance(content, TextAndImagesContent)

        # Verify actual content values
        assert content.text is not None
        assert content.text.text == "Project overview with diagrams"
        assert content.images is not None
        assert len(content.images) == 2
        assert content.images[0].url == ImageTestCases.IMAGE_FILE_PATH_PNG_1
        assert content.images[1].url == ImageTestCases.IMAGE_FILE_PATH_PNG_2

    def test_generate_context_html_content(self, html_content_memory: WorkingMemory):
        """Test generate_context with HTML content."""
        context = html_content_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # test_report + MAIN_STUFF_NAME alias
        assert "test_report" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["test_report"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact
        content = unwrap_stuff_artefact(artefact=artefact).content
        assert isinstance(content, HtmlContent)

        # Verify actual content values
        assert content.inner_html == "<h1>Test Report</h1><p>This is a <strong>test</strong> report.</p><ul><li>Item 1</li><li>Item 2</li></ul>"
        assert content.css_class == "report-content"

    def test_generate_context_number_content(self, number_content_memory: WorkingMemory):
        """Test generate_context with number content."""
        context = number_content_memory.generate_context()

        assert isinstance(context, dict)
        assert len(context) == 2  # pi_value + MAIN_STUFF_NAME alias
        assert "pi_value" in context
        assert MAIN_STUFF_NAME in context

        # Verify artefact structure
        artefact = context["pi_value"]
        assert isinstance(artefact, StuffArtefact)
        assert BaseStuffArtefactField.CONTENT_CLASS in artefact
        content = unwrap_stuff_artefact(artefact=artefact).content
        assert isinstance(content, NumberContent)

        # Verify actual content value
        assert content.number == 3.14159

    def test_generate_context_artefact_independence(self, multiple_stuff_memory: WorkingMemory):
        """Test that each stuff generates independent artefacts."""
        context = multiple_stuff_memory.generate_context()

        # Get artefacts for different stuffs
        question_artefact = context["question"]
        document_artefact = context["document"]
        diagram_artefact = context["diagram"]

        # Verify they are different objects
        assert question_artefact is not document_artefact
        assert question_artefact is not diagram_artefact
        assert document_artefact is not diagram_artefact

        # But aliases should point to the same object
        assert context[MAIN_STUFF_NAME] is document_artefact
