from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary, resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.libraries.library_crate import LibraryCrate


class TestTsZodEmitter:
    """Unit tests for the ts-zod pure types-file emitter.

    The `tsc --strict` compile gate on emitted TS lives in the `conformance/` cross-repo harness (D7);
    here we assert the structural contract of the pure types file.
    """

    def test_emits_a_pure_types_file_and_a_binder(self, pipeline_crate: LibraryCrate):
        files = emit_ts_zod(resolve_concepts_from_crate(pipeline_crate))
        assert [file.filename for file in files] == ["types.ts", "binder.ts"]
        content = files[0].content
        # types.ts is pure: imports only zod, nothing Pipelex.
        assert 'import { z } from "zod";' in content
        assert "pipelex" not in content
        assert "projection: types / ts-zod" in content

    def test_binder_validates_per_concept_over_the_types_file(self, pipeline_crate: LibraryCrate):
        binder = emit_ts_zod(resolve_concepts_from_crate(pipeline_crate))[1].content
        # The binder depends on the pure types file, not on zod directly.
        assert 'from "./types";' in binder
        assert "ReportSchema,\n  type Report," in binder
        # Keys are wire-native, so parse/serialize are a direct Schema.parse — no key remapping helper.
        assert "mapKeysDeep" not in binder
        assert "toCamel" not in binder
        assert "export function parseReport(wire: unknown): Report {" in binder
        assert "return ReportSchema.parse(wire);" in binder
        assert "export function serializeReport(value: Report): Report {" in binder

    def test_schema_and_inferred_type_per_concept(self, pipeline_crate: LibraryCrate):
        content = emit_ts_zod(resolve_concepts_from_crate(pipeline_crate))[0].content
        assert "export const ReportSchema = z.object({" in content
        assert "export type Report = z.infer<typeof ReportSchema>;" in content

    def test_concept_refs_use_lazy_and_literals_keep_defaults(self, pipeline_crate: LibraryCrate):
        content = emit_ts_zod(resolve_concepts_from_crate(pipeline_crate))[0].content
        # A concept reference is a forward-safe lazy schema; the literal-with-default is a defaulted enum.
        assert "score: z.lazy(() => ScoreSchema).optional()" in content
        assert 'status: z.enum(["draft", "final"]).default("draft")' in content

    def test_temporal_defaults_emit_iso_wire_strings(self, temporal_defaults_crate: LibraryCrate):
        content = emit_ts_zod(resolve_concepts_from_crate(temporal_defaults_crate))[0].content
        assert 'starts_on: z.string().default("2026-07-11")' in content
        assert 'recorded_at: z.string().default("2026-07-11T09:30:00")' in content
        assert 'starts_at: z.string().default("09:30:00")' in content

    def test_dict_defaults_are_canonical(self, reordered_dict_default_crates: tuple[LibraryCrate, LibraryCrate]):
        first_crate, second_crate = reordered_dict_default_crates

        first_output = emit_ts_zod(resolve_concepts_from_crate(first_crate))
        second_output = emit_ts_zod(resolve_concepts_from_crate(second_crate))

        assert first_output == second_output
        assert 'default({"alpha": "first", "zeta": "last"})' in first_output[0].content

    def test_explicitly_empty_structure_emits_an_empty_object_schema(self):
        crate = LibraryCrate(
            concepts={
                "demo.Marker": ConceptBlueprint(description="An empty marker", structure={}),
                "demo.Opaque": ConceptBlueprint(description="An opaque payload"),
            }
        )

        content = emit_ts_zod(resolve_concepts_from_crate(crate))[0].content

        assert "export const MarkerSchema = z.object({});" in content
        assert "export const OpaqueSchema = z.unknown();" in content

    def test_self_recursive_concept_uses_an_explicit_type_and_annotated_schema(self):
        crate = LibraryCrate(
            concepts={
                "graph.Node": ConceptBlueprint(
                    description="A recursive node",
                    structure={
                        "next": ConceptStructureBlueprint(
                            description="Next node",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="graph.Node",
                            required=False,
                        )
                    },
                )
            }
        )

        content = emit_ts_zod(resolve_concepts_from_crate(crate))[0].content

        assert "export type Node = {\n  next?: Node;\n};" in content
        assert "export const NodeSchema: z.ZodType<Node> = z.object({" in content

    def test_mutually_recursive_concepts_use_explicit_types_and_annotated_schemas(self):
        crate = LibraryCrate(
            concepts={
                "graph.Left": ConceptBlueprint(
                    description="Left node",
                    structure={
                        "right": ConceptStructureBlueprint(
                            description="Right node",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="graph.Right",
                            required=True,
                        )
                    },
                ),
                "graph.Right": ConceptBlueprint(
                    description="Right node",
                    structure={
                        "left": ConceptStructureBlueprint(
                            description="Left node",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="graph.Left",
                            required=True,
                        )
                    },
                ),
            }
        )

        content = emit_ts_zod(resolve_concepts_from_crate(crate))[0].content

        assert "export type Left = {\n  right: Right;\n};" in content
        assert "export const LeftSchema: z.ZodType<Left> = z.object({" in content
        assert "export type Right = {\n  left: Left;\n};" in content
        assert "export const RightSchema: z.ZodType<Right> = z.object({" in content

    def test_field_keys_are_wire_native_snake_case(self, edge_crate: LibraryCrate):
        # Keys are the crate's snake_case field names verbatim (D10) — the schema validates the wire
        # directly, with no camelCase remapping layer that could corrupt nested record/opaque data.
        content = emit_ts_zod(resolve_concepts_from_crate(edge_crate))[0].content
        assert "item_count: z.number().int()" in content
        assert "itemCount" not in content
        assert "@wire" not in content

    def test_refines_native_renders_a_lazy_base_schema(self, pipeline_crate: LibraryCrate):
        # Summary refines native.Text (kept, not flattened) — a forward-safe lazy ref to the native.
        content = emit_ts_zod(resolve_concepts_from_crate(pipeline_crate))[0].content
        assert "export const SummarySchema = z.lazy(() => TextSchema);" in content

    def test_collision_qualifies_type_names(self, edge_crate: LibraryCrate):
        content = emit_ts_zod(resolve_concepts_from_crate(edge_crate))[0].content
        assert "export const AlphaResultSchema = z.object({" in content
        assert "export const BetaResultSchema = z.object({" in content

    def test_collision_safe_names_are_shared_by_definitions_references_and_binders(self):
        concepts = [
            ResolvedConcept(
                concept_ref="foo.bar.Result",
                domain="foo.bar",
                code="Result",
                description="Hierarchical result",
                is_native=False,
                needs_qualification=True,
                base_ref="foo_bar.Result",
                fields=[],
                structureless=False,
                imprecision_reason=None,
                opaque_python_class=None,
            ),
            ResolvedConcept(
                concept_ref="foo_bar.Result",
                domain="foo_bar",
                code="Result",
                description="Underscored result",
                is_native=False,
                needs_qualification=True,
                base_ref=None,
                fields=[],
                structureless=True,
                imprecision_reason="concept declares no structure",
                opaque_python_class=None,
            ),
            ResolvedConcept(
                concept_ref="alpha.Result",
                domain="alpha",
                code="Result",
                description="Qualified result",
                is_native=False,
                needs_qualification=True,
                base_ref=None,
                fields=[],
                structureless=True,
                imprecision_reason="concept declares no structure",
                opaque_python_class=None,
            ),
            ResolvedConcept(
                concept_ref="other.AlphaResult",
                domain="other",
                code="AlphaResult",
                description="Bare alpha result",
                is_native=False,
                needs_qualification=False,
                base_ref=None,
                fields=[],
                structureless=True,
                imprecision_reason="concept declares no structure",
                opaque_python_class=None,
            ),
        ]
        forward = emit_ts_zod(ResolvedLibrary(mthds_version="0.1.0", concepts=concepts))
        reversed_output = emit_ts_zod(ResolvedLibrary(mthds_version="0.1.0", concepts=list(reversed(concepts))))

        assert forward == reversed_output
        types_content = forward[0].content
        binder_content = forward[1].content
        assert "export const FooBarResultSchema = z.lazy(() => FooBarResult2Schema);" in types_content
        assert types_content.count("export const FooBarResultSchema") == 1
        assert types_content.count("export const FooBarResult2Schema") == 1
        assert types_content.count("export const AlphaResultSchema") == 1
        assert types_content.count("export const AlphaResult2Schema") == 1
        assert binder_content.count("export function parseFooBarResult(") == 1
        assert binder_content.count("export function parseFooBarResult2(") == 1
        assert binder_content.count("export function parseAlphaResult(") == 1
        assert binder_content.count("export function parseAlphaResult2(") == 1

    def test_schema_derived_names_do_not_collide_with_authored_type_names(self):
        concepts = [
            ResolvedConcept(
                concept_ref=f"demo.{code}",
                domain="demo",
                code=code,
                description=f"{code} concept",
                is_native=False,
                needs_qualification=False,
                base_ref=None,
                fields=[],
                structureless=True,
                imprecision_reason="concept declares no structure",
                opaque_python_class=None,
            )
            for code in ("Foo", "FooSchema")
        ]

        types_file, binder_file = emit_ts_zod(ResolvedLibrary(mthds_version="0.1.0", concepts=concepts))

        assert "export const FooSchema = z.unknown();" in types_file.content
        assert "export type FooSchema2 = z.infer<typeof FooSchema2Schema>;" in types_file.content
        assert "  FooSchema,\n  type Foo," in binder_file.content
        assert "  FooSchema2Schema,\n  type FooSchema2," in binder_file.content

    def test_dict_fields_render_records_honestly(self, materialized_image_crate: LibraryCrate):
        """The DICT path — an authored unspecified-values dict and an authored typed dict — renders
        honest z.record schemas with the imprecision surfaced, never a guessed shape; the pinned
        `Image` materializes flat pixel dimensions.
        """
        content = emit_ts_zod(resolve_concepts_from_crate(materialized_image_crate))[0].content
        assert "metadata: z.record(z.string(), z.unknown()).optional()" in content
        assert "@imprecise dict value type unspecified" in content
        assert "captions: z.record(z.string(), z.string())" in content
        assert "width: z.number().int().optional()" in content

    def test_imprecision_and_opaque_are_surfaced(self, edge_crate: LibraryCrate):
        content = emit_ts_zod(resolve_concepts_from_crate(edge_crate))[0].content
        # An untyped list is an honest z.unknown() item plus a JSDoc caveat, never a guessed shape.
        assert "items: z.array(z.unknown())" in content
        assert "@imprecise list item type unspecified" in content
        # A structureless / Python-backed concept is opaque unknown, surfaced.
        assert "export const BlobSchema = z.unknown();" in content
        assert "export const LegacySchema = z.unknown();" in content
