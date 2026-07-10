from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
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

    def test_imprecision_and_opaque_are_surfaced(self, edge_crate: LibraryCrate):
        content = emit_ts_zod(resolve_concepts_from_crate(edge_crate))[0].content
        # An untyped list is an honest z.unknown() item plus a JSDoc caveat, never a guessed shape.
        assert "items: z.array(z.unknown())" in content
        assert "@imprecise list item type unspecified" in content
        # A structureless / Python-backed concept is opaque unknown, surfaced.
        assert "export const BlobSchema = z.unknown();" in content
        assert "export const LegacySchema = z.unknown();" in content
