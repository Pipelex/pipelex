from datetime import date, datetime, time
from pathlib import Path

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.libraries.library_crate import LibraryCrate
from tests.unit.pipelex.codegen.conftest import load_generated_module


class TestPythonPydanticEmitter:
    """Unit tests for the plain-pydantic types emitter (no Pipelex dependency)."""

    def test_emits_a_single_models_module(self, pipeline_crate: LibraryCrate):
        files = emit_python_pydantic(resolve_concepts_from_crate(pipeline_crate))
        assert [file.filename for file in files] == ["models.py"]

    def test_generated_module_is_pipelex_free_and_uses_modern_typing(self, pipeline_crate: LibraryCrate):
        content = emit_python_pydantic(resolve_concepts_from_crate(pipeline_crate))[0].content
        assert "pipelex" not in content
        assert "StructuredContent" not in content
        # Modern typing: builtin generics and `| None`, not typing.List / typing.Optional.
        assert "list[str] | None" in content
        assert "from typing import Optional" not in content
        assert "from typing import List" not in content

    def test_generated_module_compiles_and_validates(self, pipeline_crate: LibraryCrate, tmp_path: Path):
        content = emit_python_pydantic(resolve_concepts_from_crate(pipeline_crate))[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models")
        # Forward-referenced nested model resolves; defaults apply.
        report = module.Report(score={"value": 4.0}, label={"text": "x"})
        assert report.score.value == 4.0
        assert report.status == "draft"

    def test_temporal_defaults_generate_importable_models(self, temporal_defaults_crate: LibraryCrate, tmp_path: Path):
        content = emit_python_pydantic(resolve_concepts_from_crate(temporal_defaults_crate))[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models_temporal_defaults")
        event = module.Event()
        assert event.starts_on == date(2026, 7, 11)
        assert event.recorded_at == datetime(2026, 7, 11, 9, 30)
        assert event.starts_at == time(9, 30)

    def test_serialize_parse_round_trip(self, pipeline_crate: LibraryCrate, tmp_path: Path):
        """The generated pydantic helpers round-trip: model_dump (serialize) then model_validate (parse)
        reproduce the value. Wire names are already snake_case Python names, so no binder is needed.
        """
        module = load_generated_module(
            emit_python_pydantic(resolve_concepts_from_crate(pipeline_crate))[0].content, tmp_path=tmp_path, name="gen_models_roundtrip"
        )
        report = module.Report(score={"value": 4.0, "rationale": "high"}, label={"text": "x"}, tags=["a", "b"])
        wire = report.model_dump(mode="json")
        assert module.Report.model_validate(wire) == report

    def test_native_concept_is_emitted_as_a_model(self, pipeline_crate: LibraryCrate):
        content = emit_python_pydantic(resolve_concepts_from_crate(pipeline_crate))[0].content
        # Uniform treatment: the materialized native becomes a plain model (self-contained crate).
        assert "class Text(BaseModel):" in content

    def test_refines_native_extends_the_emitted_base(self, refines_crate: LibraryCrate, tmp_path: Path):
        content = emit_python_pydantic(resolve_concepts_from_crate(refines_crate))[0].content
        assert "class Thumbnail(Image):" in content
        # The base is defined before the subclass (inheritance is eager) and the module imports cleanly.
        load_generated_module(content, tmp_path=tmp_path, name="gen_models_refines")

    def test_dict_fields_render_honestly_and_round_trip(self, materialized_image_crate: LibraryCrate, tmp_path: Path):
        """The DICT path — both an authored unspecified-values dict (imprecision surfaced) and an
        authored typed dict — renders honest annotations in a module that compiles and round-trips,
        and the pinned `Image` materializes flat `width`/`height` integers (D11 resolution).
        """
        content = emit_python_pydantic(resolve_concepts_from_crate(materialized_image_crate))[0].content
        assert "metadata: dict[str, Any] | None" in content
        assert "imprecise: dict value type unspecified" in content
        assert "captions: dict[str, str]" in content
        assert "width: int | None" in content
        assert "height: int | None" in content
        assert "size" not in content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models_dict")
        image = module.Image(url="pipelex-storage://runs/abc/image.png", width=512, height=256)
        assert module.Image.model_validate(image.model_dump(mode="json")) == image

    def test_opaque_concepts_pass_content_through(self, edge_crate: LibraryCrate, tmp_path: Path):
        """Opaque = pass-through, never lossy (B1-1): a structureless / Python-class-backed concept
        validates any payload and keeps every field verbatim (extra="allow"), instead of pydantic's
        default extra="ignore" silently stripping the content.
        """
        content = emit_python_pydantic(resolve_concepts_from_crate(edge_crate))[0].content
        assert 'model_config = ConfigDict(extra="allow")' in content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models_opaque")
        payload = {"kind": "legacy", "nested": {"x": 1}}
        legacy = module.Legacy.model_validate(payload)
        assert legacy.model_dump() == payload
        blob = module.Blob.model_validate(payload)
        assert blob.model_dump() == payload

    def test_unresolved_refinement_passes_content_through(self, tmp_path: Path):
        crate = LibraryCrate(concepts={"consumer.ExternalReport": ConceptBlueprint(description="External report", refines="vendor->reports.Report")})
        content = emit_python_pydantic(resolve_concepts_from_crate(crate))[0].content
        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models_external_refinement")
        payload = {"kind": "external", "nested": {"score": 3}}

        report = module.ExternalReport.model_validate(payload)

        assert report.model_dump() == payload

    def test_collision_qualifies_class_names(self, edge_crate: LibraryCrate):
        content = emit_python_pydantic(resolve_concepts_from_crate(edge_crate))[0].content
        assert "class alpha__Result(BaseModel):" in content
        assert "class beta__Result(BaseModel):" in content
