from typing import Any, ClassVar, Dict, List, Tuple, cast

import pytest

from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff_content import HtmlContent, ImageContent, ListContent, NumberContent, TextAndImagesContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.core.working_memory_factory import WorkingMemoryFactory


class TestWorkingMemoryData:
    """Test data for WorkingMemory tests."""

    # Sample text content
    SAMPLE_TEXT = """
    The Dawn of Ultra-Rapid Transit: NextGen High-Speed Trains Redefine Travel
    By Eliza Montgomery, Transportation Technology Reporter

    In an era where time is increasingly precious, a revolution in rail transportation is quietly 
    transforming how we connect cities and regions. The emergence of ultra-high-speed train 
    networks, capable of speeds exceeding 350 mph, promises to render certain short-haul 
    flights obsolete while dramatically reducing carbon emissions.
    """

    # Sample PDF and image URLs
    SAMPLE_PDF_URL = "assets/extract_dpe/dpe_single_page.pdf"
    SAMPLE_IMAGE_URL = "assets/gantt_charts/sample_gantt.png"

    # Test cases for different content types
    SINGLE_TEXT_CASE = "single_text"
    SINGLE_IMAGE_CASE = "single_image"
    SINGLE_PDF_CASE = "single_pdf"
    MULTIPLE_STUFF_CASE = "multiple_stuff"
    WITH_ALIASES_CASE = "with_aliases"
    COMPLEX_LIST_CASE = "complex_list"
    TEXT_AND_IMAGES_CASE = "text_and_images"
    HTML_CONTENT_CASE = "html_content"
    NUMBER_CONTENT_CASE = "number_content"

    TEST_CASES: ClassVar[List[Tuple[str, str]]] = [
        ("Single text content", SINGLE_TEXT_CASE),
        ("Single image content", SINGLE_IMAGE_CASE),
        ("Single PDF content", SINGLE_PDF_CASE),
        ("Multiple stuff items", MULTIPLE_STUFF_CASE),
        ("WorkingMemory with aliases", WITH_ALIASES_CASE),
        ("Complex list content", COMPLEX_LIST_CASE),
        ("Text and images content", TEXT_AND_IMAGES_CASE),
        ("HTML content", HTML_CONTENT_CASE),
        ("Number content", NUMBER_CONTENT_CASE),
    ]


class TestWorkingMemory:
    """Unit tests for WorkingMemory class."""

    @pytest.fixture
    def single_text_memory(self) -> WorkingMemory:
        """Create WorkingMemory with single text content."""
        return WorkingMemoryFactory.make_from_text(text=TestWorkingMemoryData.SAMPLE_TEXT, concept_str=NativeConcept.TEXT.code, name="sample_text")

    @pytest.fixture
    def single_image_memory(self) -> WorkingMemory:
        """Create WorkingMemory with single image content."""
        return WorkingMemoryFactory.make_from_image(
            image_url=TestWorkingMemoryData.SAMPLE_IMAGE_URL, concept_str="gantt.GanttImage", name="gantt_chart_image"
        )

    @pytest.fixture
    def single_pdf_memory(self) -> WorkingMemory:
        """Create WorkingMemory with single PDF content."""
        return WorkingMemoryFactory.make_from_pdf(pdf_url=TestWorkingMemoryData.SAMPLE_PDF_URL, concept_str="PDF", name="pdf_document")

    @pytest.fixture
    def multiple_stuff_memory(self) -> WorkingMemory:
        """Create WorkingMemory with multiple stuff items."""
        text_stuff = StuffFactory.make_stuff(
            concept_str="native.Text", name="question", content=TextContent(text="What are the aerodynamic features?")
        )

        document_stuff = StuffFactory.make_stuff(
            concept_str="native.Text", name="document", content=TextContent(text=TestWorkingMemoryData.SAMPLE_TEXT)
        )

        image_stuff = StuffFactory.make_stuff(
            concept_str="native.Image", name="diagram", content=ImageContent(url=TestWorkingMemoryData.SAMPLE_IMAGE_URL)
        )

        return WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[text_stuff, document_stuff, image_stuff], main_name="document")

    @pytest.fixture
    def memory_with_aliases(self) -> WorkingMemory:
        """Create WorkingMemory with aliases."""
        text_stuff = StuffFactory.make_stuff(concept_str="native.Text", name="primary_text", content=TextContent(text="Primary content"))

        secondary_stuff = StuffFactory.make_stuff(concept_str="native.Text", name="secondary_text", content=TextContent(text="Secondary content"))

        memory = WorkingMemory()
        memory.add_new_stuff(name="primary_text", stuff=text_stuff)
        memory.add_new_stuff(name="secondary_text", stuff=secondary_stuff)
        memory.set_alias(alias="main_text", target="primary_text")
        memory.set_alias(alias="backup_text", target="secondary_text")

        return memory

    @pytest.fixture
    def complex_list_memory(self) -> WorkingMemory:
        """Create WorkingMemory with complex list content containing mixed types."""
        complex_content: ListContent[TextContent | ImageContent | NumberContent] = ListContent(
            items=[
                TextContent(text="The quick brown fox jumps over the lazy dog"),
                ImageContent(url=TestWorkingMemoryData.SAMPLE_IMAGE_URL),
                NumberContent(number=42.5),
            ]
        )

        complex_stuff = StuffFactory.make_stuff(concept_str="native.List", name="mixed_list", content=complex_content)

        return WorkingMemoryFactory.make_from_single_stuff(stuff=complex_stuff)

    @pytest.fixture
    def text_and_images_memory(self) -> WorkingMemory:
        """Create WorkingMemory with text and images content."""
        text_and_images_content = TextAndImagesContent(
            text=TextContent(text="Project overview with diagrams"),
            images=[ImageContent(url=TestWorkingMemoryData.SAMPLE_IMAGE_URL), ImageContent(url="assets/diagrams/architecture.png")],
        )

        stuff = StuffFactory.make_stuff(concept_str="native.TextAndImages", name="project_overview", content=text_and_images_content)

        return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

    @pytest.fixture
    def html_content_memory(self) -> WorkingMemory:
        """Create WorkingMemory with HTML content."""
        html_content = HtmlContent(
            inner_html="<h1>Test Report</h1><p>This is a <strong>test</strong> report.</p><ul><li>Item 1</li><li>Item 2</li></ul>",
            css_class="report-content",
        )

        stuff = StuffFactory.make_stuff(concept_str="native.Html", name="test_report", content=html_content)

        return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

    @pytest.fixture
    def number_content_memory(self) -> WorkingMemory:
        """Create WorkingMemory with number content."""
        number_content = NumberContent(number=3.14159)

        stuff = StuffFactory.make_stuff(concept_str="native.Number", name="pi_value", content=number_content)

        return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

    def test_to_reduced_memory_single_text(self, single_text_memory: WorkingMemory):
        """Test to_reduced_memory with single text content."""
        reduced_memory = single_text_memory.to_reduced_memory()
        from pipelex import pretty_print

        pretty_print(reduced_memory)

        # Should have one entry for the text content
        assert len(reduced_memory) == 1
        assert "sample_text" in reduced_memory

        # Check the dict structure
        text_blueprint = reduced_memory["sample_text"]
        assert isinstance(text_blueprint, dict)
        assert text_blueprint["concept_code"] == NativeConcept.TEXT.code

        # Check content is properly serialized - smart_dump() returns just the text string
        assert isinstance(text_blueprint["content"], str)
        assert text_blueprint["content"] == TestWorkingMemoryData.SAMPLE_TEXT

    def test_to_reduced_memory_single_image(self, single_image_memory: WorkingMemory):
        """Test to_reduced_memory with single image content."""
        reduced_memory = single_image_memory.to_reduced_memory()

        # Should have one entry for the image content
        assert len(reduced_memory) == 1
        assert "gantt_chart_image" in reduced_memory

        # Check the dict structure
        image_blueprint = reduced_memory["gantt_chart_image"]
        assert isinstance(image_blueprint, dict)
        assert image_blueprint["concept_code"] == "gantt.GanttImage"

        # Check content is properly serialized
        assert isinstance(image_blueprint["content"], dict)
        assert "url" in image_blueprint["content"]
        assert image_blueprint["content"]["url"] == TestWorkingMemoryData.SAMPLE_IMAGE_URL

    def test_to_reduced_memory_single_pdf(self, single_pdf_memory: WorkingMemory):
        """Test to_reduced_memory with single PDF content."""
        reduced_memory = single_pdf_memory.to_reduced_memory()

        # Should have one entry for the PDF content
        assert len(reduced_memory) == 1
        assert "pdf_document" in reduced_memory

        # Check the dict structure
        pdf_blueprint = reduced_memory["pdf_document"]
        assert isinstance(pdf_blueprint, dict)
        assert pdf_blueprint["concept_code"] == "native.PDF"

        # Check content is properly serialized
        assert isinstance(pdf_blueprint["content"], dict)
        assert "url" in pdf_blueprint["content"]
        assert pdf_blueprint["content"]["url"] == TestWorkingMemoryData.SAMPLE_PDF_URL

    def test_to_reduced_memory_multiple_stuff(self, multiple_stuff_memory: WorkingMemory):
        """Test to_reduced_memory with multiple stuff items."""
        reduced_memory = multiple_stuff_memory.to_reduced_memory()

        # Should have three entries for the three stuff items
        assert len(reduced_memory) == 3
        assert "question" in reduced_memory
        assert "document" in reduced_memory
        assert "diagram" in reduced_memory

        # Check each item is properly converted
        question_blueprint = reduced_memory["question"]
        assert question_blueprint["concept_code"] == "native.Text"
        assert isinstance(question_blueprint["content"], str)
        assert question_blueprint["content"] == "What are the aerodynamic features?"

        document_blueprint = reduced_memory["document"]
        assert document_blueprint["concept_code"] == "native.Text"
        assert isinstance(document_blueprint["content"], str)
        assert document_blueprint["content"] == TestWorkingMemoryData.SAMPLE_TEXT

        diagram_blueprint = reduced_memory["diagram"]
        assert diagram_blueprint["concept_code"] == "native.Image"
        assert isinstance(diagram_blueprint["content"], dict)
        assert diagram_blueprint["content"]["url"] == TestWorkingMemoryData.SAMPLE_IMAGE_URL

    def test_to_reduced_memory_excludes_aliases(self, memory_with_aliases: WorkingMemory):
        """Test to_reduced_memory excludes aliases (only includes root items)."""
        reduced_memory = memory_with_aliases.to_reduced_memory()

        # Should only have the root items, not the aliases
        assert len(reduced_memory) == 2
        assert "primary_text" in reduced_memory
        assert "secondary_text" in reduced_memory

        # Aliases should not be included
        assert "main_text" not in reduced_memory
        assert "backup_text" not in reduced_memory

        # Check content is correct
        primary_blueprint = reduced_memory["primary_text"]
        assert primary_blueprint["concept_code"] == "native.Text"
        assert isinstance(primary_blueprint["content"], str)
        assert primary_blueprint["content"] == "Primary content"

        secondary_blueprint = reduced_memory["secondary_text"]
        assert secondary_blueprint["concept_code"] == "native.Text"
        assert isinstance(secondary_blueprint["content"], str)
        assert secondary_blueprint["content"] == "Secondary content"

    def test_to_reduced_memory_empty_working_memory(self):
        """Test to_reduced_memory with empty WorkingMemory."""
        empty_memory = WorkingMemoryFactory.make_empty()
        reduced_memory = empty_memory.to_reduced_memory()

        # Should return empty dictionary
        assert len(reduced_memory) == 0
        assert isinstance(reduced_memory, dict)

    def test_to_reduced_memory_return_type(self, single_text_memory: WorkingMemory):
        """Test that to_reduced_memory returns correct type."""
        reduced_memory = single_text_memory.to_reduced_memory()

        # Check return type
        assert isinstance(reduced_memory, dict)

        # Check each value is a dict with the expected structure
        for key, value in reduced_memory.items():
            assert isinstance(key, str)
            assert isinstance(value, dict)
            assert "concept_code" in value
            assert "content" in value

    def test_to_reduced_memory_complex_list(self, complex_list_memory: WorkingMemory):
        """Test to_reduced_memory with complex list containing mixed content types."""
        reduced_memory = complex_list_memory.to_reduced_memory()

        # Should have one entry for the list content
        assert len(reduced_memory) == 1
        assert "mixed_list" in reduced_memory

        # Check the dict structure
        list_blueprint = reduced_memory["mixed_list"]
        assert isinstance(list_blueprint, dict)
        assert list_blueprint["concept_code"] == "native.List"

        # Check content is properly serialized
        assert isinstance(list_blueprint["content"], dict)
        assert "items" in list_blueprint["content"]
        items = cast(List[Dict[str, Any]], list_blueprint["content"]["items"])
        assert len(items) == 3

        # Verify each item is properly serialized
        text_item = items[0]
        assert text_item["text"] == "The quick brown fox jumps over the lazy dog"

        image_item = items[1]
        assert image_item["url"] == TestWorkingMemoryData.SAMPLE_IMAGE_URL

        number_item = items[2]
        assert number_item["number"] == 42.5

        # Ensure no __module__ or __class__ fields are present
        assert "__module__" not in list_blueprint["content"]
        assert "__class__" not in list_blueprint["content"]

    def test_to_reduced_memory_text_and_images(self, text_and_images_memory: WorkingMemory):
        """Test to_reduced_memory with text and images content."""
        reduced_memory = text_and_images_memory.to_reduced_memory()

        # Should have one entry for the text and images content
        assert len(reduced_memory) == 1
        assert "project_overview" in reduced_memory

        # Check the dict structure
        content_blueprint = reduced_memory["project_overview"]
        assert isinstance(content_blueprint, dict)
        assert content_blueprint["concept_code"] == "native.TextAndImages"

        # Check content is properly serialized
        content = content_blueprint["content"]
        assert isinstance(content, dict)
        assert "text" in content
        assert content["text"]["text"] == "Project overview with diagrams"
        assert "images" in content
        images = cast(List[Dict[str, Any]], content["images"])
        assert len(images) == 2

        # Verify image URLs
        assert images[0]["url"] == TestWorkingMemoryData.SAMPLE_IMAGE_URL
        assert images[1]["url"] == "assets/diagrams/architecture.png"

    def test_to_reduced_memory_html_content(self, html_content_memory: WorkingMemory):
        """Test to_reduced_memory with HTML content."""
        reduced_memory = html_content_memory.to_reduced_memory()

        # Should have one entry for the HTML content
        assert len(reduced_memory) == 1
        assert "test_report" in reduced_memory

        # Check the dict structure
        html_blueprint = reduced_memory["test_report"]
        assert isinstance(html_blueprint, dict)
        assert html_blueprint["concept_code"] == "native.Html"

        # Check content is properly serialized
        content = html_blueprint["content"]
        assert isinstance(content, dict)
        assert "inner_html" in content
        assert "css_class" in content
        assert "<h1>Test Report</h1>" in content["inner_html"]
        assert "<strong>test</strong>" in content["inner_html"]
        assert content["css_class"] == "report-content"

    def test_to_reduced_memory_number_content(self, number_content_memory: WorkingMemory):
        """Test to_reduced_memory with number content."""
        reduced_memory = number_content_memory.to_reduced_memory()

        # Should have one entry for the number content
        assert len(reduced_memory) == 1
        assert "pi_value" in reduced_memory

        # Check the dict structure
        number_blueprint = reduced_memory["pi_value"]
        assert isinstance(number_blueprint, dict)
        assert number_blueprint["concept_code"] == "native.Number"

        # Check content is properly serialized
        content = number_blueprint["content"]
        assert isinstance(content, dict)
        assert "number" in content
        assert content["number"] == 3.14159

    @pytest.mark.parametrize("description,test_case", TestWorkingMemoryData.TEST_CASES)
    def test_to_reduced_memory_parametrized(
        self,
        description: str,
        test_case: str,
        single_text_memory: WorkingMemory,
        single_image_memory: WorkingMemory,
        single_pdf_memory: WorkingMemory,
        multiple_stuff_memory: WorkingMemory,
        memory_with_aliases: WorkingMemory,
        complex_list_memory: WorkingMemory,
        text_and_images_memory: WorkingMemory,
        html_content_memory: WorkingMemory,
        number_content_memory: WorkingMemory,
    ):
        """Parametrized test for different memory types."""
        memory_map = {
            TestWorkingMemoryData.SINGLE_TEXT_CASE: single_text_memory,
            TestWorkingMemoryData.SINGLE_IMAGE_CASE: single_image_memory,
            TestWorkingMemoryData.SINGLE_PDF_CASE: single_pdf_memory,
            TestWorkingMemoryData.MULTIPLE_STUFF_CASE: multiple_stuff_memory,
            TestWorkingMemoryData.WITH_ALIASES_CASE: memory_with_aliases,
            TestWorkingMemoryData.COMPLEX_LIST_CASE: complex_list_memory,
            TestWorkingMemoryData.TEXT_AND_IMAGES_CASE: text_and_images_memory,
            TestWorkingMemoryData.HTML_CONTENT_CASE: html_content_memory,
            TestWorkingMemoryData.NUMBER_CONTENT_CASE: number_content_memory,
        }

        memory = memory_map[test_case]
        reduced_memory = memory.to_reduced_memory()

        # Basic assertions that should work for all cases
        assert isinstance(reduced_memory, dict)
        assert len(reduced_memory) >= 0

        # All values should be dicts with the expected structure
        for key, value in reduced_memory.items():
            assert isinstance(key, str)
            assert isinstance(value, dict)
            assert isinstance(value["concept_code"], str)
            assert value["content"] is not None

            # Ensure no __module__ or __class__ fields are present in any content
            if isinstance(value["content"], dict):
                assert "__module__" not in value["content"]
                assert "__class__" not in value["content"]
