from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.codegen.resolved_fields import ResolvedTypeKind, iter_imprecision_reasons
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.libraries.library_crate import LibraryCrate


class TestResolvedConcepts:
    """Unit tests for resolving a normalized crate into the neutral emitter input."""

    def test_pipeline_concepts_resolve_with_native_and_qualified_refs(self, pipeline_crate: LibraryCrate):
        library = resolve_concepts_from_crate(pipeline_crate)
        by_ref = library.by_ref()

        assert library.mthds_version == "1.0.0-test"
        # The referenced native was materialized into the crate and is flagged native.
        assert by_ref["native.Text"].is_native is True
        # Unique codes need no qualification.
        assert by_ref["pipeline.Report"].needs_qualification is False

        report = by_ref["pipeline.Report"]
        assert report.structureless is False
        fields = {field.name: field for field in report.fields}
        # In-body concept ref is qualified; the native ref is flagged native.
        assert fields["score"].resolved_type.kind is ResolvedTypeKind.CONCEPT
        assert fields["score"].resolved_type.concept_ref == "pipeline.Score"
        assert fields["label"].resolved_type.concept_ref == "native.Text"
        assert fields["label"].resolved_type.is_native is True
        # The literal-with-default keeps its default.
        assert fields["status"].resolved_type.kind is ResolvedTypeKind.LITERAL
        assert fields["status"].default_value == "draft"

    def test_cross_domain_collision_flags_qualification(self, edge_crate: LibraryCrate):
        library = resolve_concepts_from_crate(edge_crate)
        by_ref = library.by_ref()
        # A code shared across two domains forces qualification on both.
        assert by_ref["alpha.Result"].needs_qualification is True
        assert by_ref["beta.Result"].needs_qualification is True
        # A code unique to one domain does not.
        assert by_ref["alpha.Blob"].needs_qualification is False

    def test_imprecise_field_carries_a_reason(self, edge_crate: LibraryCrate):
        result = resolve_concepts_from_crate(edge_crate).by_ref()["alpha.Result"]
        items_field = next(field for field in result.fields if field.name == "items")
        reasons = iter_imprecision_reasons(items_field.resolved_type)
        assert reasons
        assert "unspecified" in reasons[0]

    def test_structureless_concept_is_opaque_with_a_reason(self, edge_crate: LibraryCrate):
        blob = resolve_concepts_from_crate(edge_crate).by_ref()["alpha.Blob"]
        assert blob.structureless is True
        assert blob.fields == []
        assert blob.opaque_python_class is None
        assert blob.imprecision_reason is not None

    def test_python_backed_concept_is_surfaced_not_silently_emitted(self, edge_crate: LibraryCrate):
        legacy = resolve_concepts_from_crate(edge_crate).by_ref()["alpha.Legacy"]
        assert legacy.structureless is True
        assert legacy.opaque_python_class == "MyLegacyClass"
        assert "MyLegacyClass" in (legacy.imprecision_reason or "")

    def test_refines_native_keeps_base_ref(self, refines_crate: LibraryCrate):
        thumbnail = resolve_concepts_from_crate(refines_crate).by_ref()["media.Thumbnail"]
        assert thumbnail.base_ref == "native.Image"
        assert thumbnail.structureless is False
        assert thumbnail.fields == []

    def test_unresolved_refinement_is_opaque(self):
        crate = LibraryCrate(concepts={"consumer.ExternalReport": ConceptBlueprint(description="External report", refines="vendor->reports.Report")})

        report = resolve_concepts_from_crate(crate).by_ref()["consumer.ExternalReport"]

        assert report.base_ref == "vendor->reports.Report"
        assert report.structureless is True
        assert report.fields == []
        assert "not available in this crate" in (report.imprecision_reason or "")
