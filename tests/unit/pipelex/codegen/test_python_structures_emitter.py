from pathlib import Path
from typing import Any

from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.libraries.library_crate import LibraryCrate
from tests.unit.pipelex.codegen.conftest import load_generated_module


class TestPythonStructuresEmitter:
    """Unit tests for the python-structures (runtime StructuredContent) types emitter."""

    def test_emits_a_single_structures_module(self, pipeline_crate: LibraryCrate):
        files = emit_python_structures(resolve_concepts_from_crate(pipeline_crate))
        assert [file.filename for file in files] == ["structures.py"]

    def test_header_carries_the_extension_file_story(self, pipeline_crate: LibraryCrate):
        content = emit_python_structures(resolve_concepts_from_crate(pipeline_crate))[0].content
        assert "DO NOT EDIT" in content
        assert "subclass" in content
        assert "projection: types / python-structures" in content

    def test_generated_module_compiles_and_builds_runtime_classes(self, pipeline_crate: LibraryCrate, tmp_path: Path):
        content = emit_python_structures(resolve_concepts_from_crate(pipeline_crate))[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_structures")
        report_cls: Any = module.Report
        # MRO check by name (avoids narrowing the runtime-only class away from its generated params).
        assert "StructuredContent" in {base.__name__ for base in report_cls.__mro__}
        # Cross-concept forward ref (Score) and native mapping (label -> TextContent) both resolve.
        report: Any = report_cls(score={"value": 2.0}, label={"text": "hi"}, status="draft")
        assert report.score.value == 2.0
        assert type(report.label).__name__ == "TextContent"

    def test_native_concept_is_not_re_emitted(self, pipeline_crate: LibraryCrate):
        content = emit_python_structures(resolve_concepts_from_crate(pipeline_crate))[0].content
        # native.Text maps to the runtime TextContent (imported), never a re-declared class.
        assert "class Text(" not in content
        assert "from pipelex.core.stuffs.text_content import TextContent" in content

    def test_refines_native_becomes_content_base_class(self, refines_crate: LibraryCrate):
        content = emit_python_structures(resolve_concepts_from_crate(refines_crate))[0].content
        assert "class Thumbnail(ImageContent):" in content

    def test_collision_qualifies_class_names(self, edge_crate: LibraryCrate):
        content = emit_python_structures(resolve_concepts_from_crate(edge_crate))[0].content
        assert "class alpha__Result(" in content
        assert "class beta__Result(" in content

    def test_typed_dict_field_maps_to_dict_annotation(self, materialized_image_crate: LibraryCrate, tmp_path: Path):
        """An authored typed dict renders the runtime Dict annotation (natives are skipped by this
        emitter, so the authored concept is the DICT path's only route here) and builds at runtime.
        """
        content = emit_python_structures(resolve_concepts_from_crate(materialized_image_crate))[0].content
        assert "captions: Dict[str, str]" in content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_structures_dict")
        gallery: Any = module.Gallery(captions={"p1": "sunset"})
        assert gallery.captions == {"p1": "sunset"}

    def test_imprecision_and_opaque_are_surfaced(self, edge_crate: LibraryCrate, tmp_path: Path):
        content = emit_python_structures(resolve_concepts_from_crate(edge_crate))[0].content
        assert "# imprecise: list item type unspecified" in content
        assert "Imprecise: concept is backed by the Python class 'MyLegacyClass'" in content
        # Still valid, importable Python despite the opaque concepts.
        load_generated_module(content, tmp_path=tmp_path, name="gen_structures_edge")
