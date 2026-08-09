"""Tests for TemplateDocumentAnalyzer service."""

from pathlib import Path
from typing import Callable

from pipelex.kernel.prompt_references import DocumentReferenceKind
from pipelex.pipe_operators.llm.template_document_analyzer import TemplateDocumentAnalyzer


class TestTemplateDocumentAnalyzer:
    """Tests for TemplateDocumentAnalyzer.analyze_template_for_documents()."""

    # --------------------------------------------------------------------------
    # Direct Document References
    # --------------------------------------------------------------------------

    def test_single_document_variable_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that a single Document variable creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Analyze this document:\n@document",
            input_specs={"document": "Document"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "document"
        assert result[0].kind == DocumentReferenceKind.DIRECT

    def test_document_list_input_creates_direct_list_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document[] input creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Analyze these documents: $documents",
            input_specs={"documents": "Document[]"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "documents"
        assert result[0].kind == DocumentReferenceKind.DIRECT_LIST

    def test_multiple_direct_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test multiple direct document references in same template."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Compare:\n@doc_a\nwith:\n@doc_b",
            input_specs={"doc_a": "Document", "doc_b": "Document"},
            domain_code="test_pipes",
        )

        assert len(result) == 2
        paths = {ref.variable_path for ref in result}
        assert paths == {"doc_a", "doc_b"}
        for ref in result:
            assert ref.kind == DocumentReferenceKind.DIRECT

    # --------------------------------------------------------------------------
    # No Documents Cases
    # --------------------------------------------------------------------------

    def test_plain_text_variable_no_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that plain Text variable does NOT create document reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Process this:\n@text",
            input_specs={"text": "Text"},
            domain_code="test_pipes",
        )

        assert len(result) == 0

    def test_image_variable_no_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image variable does NOT create document reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Look at:\n@image",
            input_specs={"image": "Image"},
            domain_code="test_pipes",
        )

        assert len(result) == 0

    def test_template_without_document_inputs(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test template with no document-related inputs."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Hello $name, your age is $age",
            input_specs={"name": "Text", "age": "Text"},
            domain_code="test_pipes",
        )

        assert len(result) == 0

    # --------------------------------------------------------------------------
    # Template Syntax Variations
    # --------------------------------------------------------------------------

    def test_dollar_syntax_document(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test $variable syntax for document."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Analyze: $report",
            input_specs={"report": "Document"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].kind == DocumentReferenceKind.DIRECT

    def test_at_syntax_document(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test @variable syntax for document."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Analyze:\n@report",
            input_specs={"report": "Document"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].kind == DocumentReferenceKind.DIRECT

    def test_jinja2_syntax_document(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test {{ variable }} Jinja2 syntax for document."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Analyze: {{ report }}",
            input_specs={"report": "Document"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].kind == DocumentReferenceKind.DIRECT

    # --------------------------------------------------------------------------
    # Mixed with Images
    # --------------------------------------------------------------------------

    def test_document_and_image_both_detected(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that documents and images are both correctly identified (docs only returned)."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # This analyzer should only return document references
        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Document:\n@doc\nImage:\n@image",
            input_specs={"doc": "Document", "image": "Image"},
            domain_code="test_pipes",
        )

        # Should only have document reference, not image
        assert len(result) == 1
        assert result[0].variable_path == "doc"
        assert result[0].kind == DocumentReferenceKind.DIRECT

    def test_only_document_detected_when_image_not_in_inputs(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that only document reference is returned when template has both but only doc in inputs."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        result = TemplateDocumentAnalyzer.analyze_template_for_documents(
            template_source="Document:\n@doc\nOther:\n@other",
            input_specs={"doc": "Document", "other": "Text"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "doc"
