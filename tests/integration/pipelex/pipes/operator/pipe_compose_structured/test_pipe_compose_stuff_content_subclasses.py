"""Integration tests for PipeCompose with various StuffContent subclasses.

These tests verify that PipeCompose correctly handles different StuffContent subclasses:
- ImageContent: image URL and metadata
- DocumentContent: document reference
- NumberContent: numeric values
- MermaidContent: diagram code
- HtmlContent: HTML fragments
- JSONContent: JSON data
- Mixed compositions with multiple StuffContent types
- Lists of StuffContent subclasses
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.mermaid_content import MermaidContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.urls import URLs
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.test_data import StuffContentSubclassTestData


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeStuffContentSubclasses:
    """Integration tests for StuffContent subclass composition in PipeCompose."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the test library for these tests."""
        return [Path("tests/integration/pipelex/pipes/operator/pipe_compose_structured")]

    async def test_compose_image_content_single(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with a single ImageContent field."""
        load_test_library(test_library_path)

        cover_image = ImageContent(
            url=URLs.jpg_example_1,
            caption="Cover photo",
            mime_type="image/jpeg",
        )
        cover_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.IMAGE),
            content=cover_image,
            name="cover",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="cover", stuff=cover_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose image gallery with single image",
                "inputs": {"cover": "Image"},
                "construct": StuffContentSubclassTestData.IMAGE_GALLERY_SINGLE_CONSTRUCT,
                "output": "compose_structured_test.ImageGallery",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_image_single",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "ImageGallery"

        gallery = main_stuff.content
        assert gallery.gallery_name == "Simple Gallery"  # type: ignore[attr-defined]
        assert isinstance(gallery.cover_image, ImageContent)  # type: ignore[attr-defined]
        assert gallery.cover_image.url == URLs.jpg_example_1  # type: ignore[attr-defined]
        assert gallery.cover_image.caption == "Cover photo"  # type: ignore[attr-defined]

    async def test_compose_image_content_multiple(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with multiple ImageContent fields."""
        load_test_library(test_library_path)

        cover_image = ImageContent(
            url=URLs.jpg_example_1,
            caption="Cover photo",
        )
        featured_image = ImageContent(
            url=URLs.png_example_1,
            caption="Featured image",
            source_prompt="A beautiful landscape",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="cover",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=cover_image,
                name="cover",
            ),
        )
        working_memory.add_new_stuff(
            name="featured",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=featured_image,
                name="featured",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose image gallery with multiple images",
                "inputs": {"cover": "Image", "featured": "Image"},
                "construct": StuffContentSubclassTestData.IMAGE_GALLERY_CONSTRUCT,
                "output": "compose_structured_test.ImageGallery",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_image_multiple",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        gallery = main_stuff.content
        assert gallery.gallery_name == "Nature Gallery"  # type: ignore[attr-defined]
        assert gallery.cover_image.url == URLs.jpg_example_1  # type: ignore[attr-defined]
        assert gallery.featured_image.url == URLs.png_example_1  # type: ignore[attr-defined]
        assert gallery.featured_image.source_prompt == "A beautiful landscape"  # type: ignore[attr-defined]

        pretty_print(gallery, title="ImageGallery - Multiple ImageContent")

    async def test_compose_pdf_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with DocumentContent fields."""
        load_test_library(test_library_path)

        main_pdf = DocumentContent(url=URLs.pdf_example_1)
        supplement_pdf = DocumentContent(url=URLs.pdf_example_2)

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="main_pdf",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=main_pdf,
                name="main_pdf",
            ),
        )
        working_memory.add_new_stuff(
            name="supplement_pdf",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=supplement_pdf,
                name="supplement_pdf",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose document archive with document content",
                "inputs": {"main_pdf": "Document", "supplement_pdf": "Document"},
                "construct": StuffContentSubclassTestData.DOCUMENT_ARCHIVE_CONSTRUCT,
                "output": "compose_structured_test.DocumentArchive",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_pdf",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        archive = main_stuff.content
        assert archive.archive_name == "Legal Documents Archive"  # type: ignore[attr-defined]
        assert isinstance(archive.main_document, DocumentContent)  # type: ignore[attr-defined]
        assert archive.main_document.url == URLs.pdf_example_1  # type: ignore[attr-defined]
        assert archive.supplementary_doc.url == URLs.pdf_example_2  # type: ignore[attr-defined]

        pretty_print(archive, title="DocumentArchive - DocumentContent")

    async def test_compose_number_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with NumberContent fields."""
        load_test_library(test_library_path)

        primary_metric = NumberContent(number=42.5)
        secondary_metric = NumberContent(number=100)

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="primary_metric",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.NUMBER),
                content=primary_metric,
                name="primary_metric",
            ),
        )
        working_memory.add_new_stuff(
            name="secondary_metric",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.NUMBER),
                content=secondary_metric,
                name="secondary_metric",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose metrics with number content",
                "inputs": {"primary_metric": "Number", "secondary_metric": "Number"},
                "construct": StuffContentSubclassTestData.METRICS_CONSTRUCT,
                "output": "compose_structured_test.Metrics",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_number",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        metrics = main_stuff.content
        assert metrics.metric_name == "Performance Metrics"  # type: ignore[attr-defined]
        assert isinstance(metrics.primary_value, NumberContent)  # type: ignore[attr-defined]
        assert metrics.primary_value.number == 42.5  # type: ignore[attr-defined]
        assert metrics.secondary_value.number == 100  # type: ignore[attr-defined]

        pretty_print(metrics, title="Metrics - NumberContent")

    async def test_compose_mermaid_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with MermaidContent field."""
        load_test_library(test_library_path)

        mermaid_diagram = MermaidContent(
            mermaid_code="graph TD\n    A[Start] --> B[End]",
            mermaid_url="https://mermaid.ink/img/...",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="mermaid_diagram",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=mermaid_diagram,
                name="mermaid_diagram",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose code snippet with mermaid diagram",
                "inputs": {"mermaid_diagram": "Text"},
                "construct": StuffContentSubclassTestData.CODE_SNIPPET_CONSTRUCT,
                "output": "compose_structured_test.CodeSnippet",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_mermaid",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        snippet = main_stuff.content
        assert snippet.snippet_name == "Architecture Diagram"  # type: ignore[attr-defined]
        assert isinstance(snippet.diagram, MermaidContent)  # type: ignore[attr-defined]
        assert "graph TD" in snippet.diagram.mermaid_code  # type: ignore[attr-defined]

        pretty_print(snippet, title="CodeSnippet - MermaidContent")

    async def test_compose_html_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with HtmlContent field."""
        load_test_library(test_library_path)

        html_content = HtmlContent(
            inner_html="<h1>Welcome</h1><p>Hello World!</p>",
            css_class="main-content",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="html_content",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=html_content,
                name="html_content",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose web content with HTML block",
                "inputs": {"html_content": "Text"},
                "construct": StuffContentSubclassTestData.WEB_CONTENT_CONSTRUCT,
                "output": "compose_structured_test.WebContent",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_html",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        web_content = main_stuff.content
        assert web_content.content_title == "Homepage Section"  # type: ignore[attr-defined]
        assert isinstance(web_content.html_block, HtmlContent)  # type: ignore[attr-defined]
        assert "<h1>Welcome</h1>" in web_content.html_block.inner_html  # type: ignore[attr-defined]
        assert web_content.html_block.css_class == "main-content"  # type: ignore[attr-defined]

        pretty_print(web_content, title="WebContent - HtmlContent")

    async def test_compose_json_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with JSONContent field."""
        load_test_library(test_library_path)

        json_data = JSONContent(
            json_obj={
                "status": "success",
                "data": {"id": 123, "name": "Test Item"},
                "metadata": {"timestamp": "2024-01-01T00:00:00Z"},
            }
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="json_data",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.JSON),
                content=json_data,
                name="json_data",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose data payload with JSON content",
                "inputs": {"json_data": "JSON"},
                "construct": StuffContentSubclassTestData.DATA_PAYLOAD_CONSTRUCT,
                "output": "compose_structured_test.DataPayload",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_json",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        payload = main_stuff.content
        assert payload.payload_name == "API Response"  # type: ignore[attr-defined]
        assert isinstance(payload.data, JSONContent)  # type: ignore[attr-defined]
        assert payload.data.json_obj["status"] == "success"  # type: ignore[attr-defined]
        assert payload.data.json_obj["data"]["id"] == 123  # type: ignore[attr-defined]

        pretty_print(payload, title="DataPayload - JSONContent")

    async def test_compose_mixed_media(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with multiple different StuffContent types."""
        load_test_library(test_library_path)

        cover_image = ImageContent(url=URLs.jpg_example_1, caption="Report Cover")
        main_pdf = DocumentContent(url=URLs.pdf_example_1)
        view_count = NumberContent(number=1500)

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="cover",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=cover_image,
                name="cover",
            ),
        )
        working_memory.add_new_stuff(
            name="main_pdf",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=main_pdf,
                name="main_pdf",
            ),
        )
        working_memory.add_new_stuff(
            name="primary_metric",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.NUMBER),
                content=view_count,
                name="primary_metric",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose mixed media report",
                "inputs": {"cover": "Image", "main_pdf": "Document", "primary_metric": "Number"},
                "construct": StuffContentSubclassTestData.MIXED_MEDIA_CONSTRUCT,
                "output": "compose_structured_test.MixedMediaReport",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_mixed_media",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        report = main_stuff.content
        assert report.report_title == "Annual Report"  # type: ignore[attr-defined]
        assert isinstance(report.cover_image, ImageContent)  # type: ignore[attr-defined]
        assert isinstance(report.document, DocumentContent)  # type: ignore[attr-defined]
        assert isinstance(report.view_count, NumberContent)  # type: ignore[attr-defined]
        assert report.cover_image.url == URLs.jpg_example_1  # type: ignore[attr-defined]
        assert report.document.url == URLs.pdf_example_1  # type: ignore[attr-defined]
        assert report.view_count.number == 1500  # type: ignore[attr-defined]

        pretty_print(report, title="MixedMediaReport - Multiple StuffContent types")

    async def test_compose_image_list(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with a list of ImageContent."""
        load_test_library(test_library_path)

        image_list = ListContent[ImageContent](
            items=[
                ImageContent(url=URLs.jpg_example_1, caption="Image 1"),
                ImageContent(url=URLs.jpg_example_2, caption="Image 2"),
                ImageContent(url=URLs.jpg_example_3, caption="Image 3"),
            ]
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="image_list",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=image_list,
                name="image_list",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose gallery with list of images",
                "inputs": {"image_list": "Image"},
                "construct": StuffContentSubclassTestData.IMAGE_LIST_GALLERY_CONSTRUCT,
                "output": "compose_structured_test.ImageListGallery",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_image_list",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        gallery = main_stuff.content
        assert gallery.gallery_name == "Photo Collection"  # type: ignore[attr-defined]
        assert isinstance(gallery.images, list)  # type: ignore[attr-defined]
        assert len(gallery.images) == 3  # type: ignore[attr-defined]
        assert gallery.images[0].url == URLs.jpg_example_1  # type: ignore[attr-defined]
        assert gallery.images[1].caption == "Image 2"  # type: ignore[attr-defined]

        pretty_print(gallery, title="ImageListGallery - List of ImageContent")

    async def test_compose_pdf_list(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test composing a StructuredContent with a list of DocumentContent."""
        load_test_library(test_library_path)

        pdf_list = ListContent[DocumentContent](
            items=[
                DocumentContent(url=URLs.pdf_example_1),
                DocumentContent(url=URLs.pdf_example_2),
            ]
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(
            name="pdf_list",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=pdf_list,
                name="pdf_list",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose bundle with list of PDFs",
                "inputs": {"pdf_list": "Document"},
                "construct": StuffContentSubclassTestData.DOCUMENT_BUNDLE_CONSTRUCT,
                "output": "compose_structured_test.DocumentBundle",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_pdf_list",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        bundle = main_stuff.content
        assert bundle.bundle_name == "Contract Bundle"  # type: ignore[attr-defined]
        assert isinstance(bundle.documents, list)  # type: ignore[attr-defined]
        assert len(bundle.documents) == 2  # type: ignore[attr-defined]
        assert bundle.documents[0].url == URLs.pdf_example_1  # type: ignore[attr-defined]

        pretty_print(bundle, title="DocumentBundle - List of DocumentContent")
