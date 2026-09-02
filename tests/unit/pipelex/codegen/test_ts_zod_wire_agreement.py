"""The ts-zod projection must accept the payload the runtime actually puts on the wire.

The two sides read one authored crate. `ConceptFactory` builds the class an interpreted run stores in
memory, and that class annotates every non-required field `X | None`; the transport dump keeps nulls on
purpose (`dump_for_transport()` is a `model_dump(serialize_as_any=True)` with no `exclude_none`, and the
composer spells `exclude_none=False` at its dump sites). So an unset optional field reaches a consumer as
an explicit `"key": null`. `emit_ts_zod` writes the schema that consumer parses it with — and `.optional()`
means `T | undefined` in zod, which *rejects* an explicit null. A projection that spelled it that way would
refuse the engine's own output, with nothing in this repo going red.

Three layers, on one shared crate:

1. **Wire pin** — build the runtime class and dump it the way transport does, asserting the unset keys are
   present and null. This is the fact the projection must accommodate; if the transport dump ever flips to
   `exclude_none`, this reddens and forces the projection decision to be revisited alongside it.
2. **Projection pin** — emit ts-zod for the same crate and require every non-required field to be
   null-tolerant. Paired with (1), the cross-language contract is encoded here even where CI has no node.
3. **Executable round-trip** — feed (1)'s JSON through the emitted schema under a real zod. Mandatory
   wherever the node toolchain is provisioned (`make test-ts-gates`, which is what CI runs); opportunistic
   on a machine without it, where the two always-on pins hold the line.
"""

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from typing import Any

import pytest

from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.helpers.ts_toolchain import resolve_node, resolve_zod_package
from tests.unit.pipelex.codegen.conftest import CRATE_TEST_VERSION

_DOMAIN = "wire"

# One authored source, read by both sides. Declaration order matters for the runtime reader only:
# `Payload` references `Detail`, so `Detail`'s generated class has to be registered first.
_AUTHORED: dict[str, ConceptBlueprint] = {
    "Detail": ConceptBlueprint(
        description="A nested detail",
        structure={
            "caption": ConceptStructureBlueprint(description="A caption", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "weight": ConceptStructureBlueprint(description="How much it counts", type=ConceptStructureBlueprintFieldType.NUMBER, required=False),
        },
    ),
    "Payload": ConceptBlueprint(
        description="A payload covering every presence spelling the wire carries",
        structure={
            "title": ConceptStructureBlueprint(description="Title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "note": ConceptStructureBlueprint(description="An optional note", type=ConceptStructureBlueprintFieldType.TEXT, required=False),
            "detail": ConceptStructureBlueprint(
                description="A nested detail", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Detail", required=False
            ),
            "tags": ConceptStructureBlueprint(
                description="Free-form tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=False
            ),
            "counts": ConceptStructureBlueprint(
                description="Counts by key",
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type="text",
                value_type="integer",
                required=False,
            ),
            "status": ConceptStructureBlueprint(description="Review status", choices=["draft", "final"], default_value="draft"),
        },
    ),
}

# Every non-required field of `Payload`, i.e. every key the runtime can put on the wire as an explicit null.
_NON_REQUIRED_FIELDS = ("note", "detail", "tags", "counts", "status")


def _authored_crate() -> LibraryCrate:
    return LibraryCrate(
        concepts={f"{_DOMAIN}.{code}": blueprint for code, blueprint in _AUTHORED.items()},
        domains={_DOMAIN: DomainBlueprint(code=_DOMAIN, description="Wire agreement domain")},
    )


class TestTsZodWireAgreement:
    @pytest.fixture
    def wire_payloads(self, load_empty_library: Any) -> list[dict[str, Any]]:
        """What the runtime hands to transport for two ordinary instances, unset optionals and all.

        The first leaves every optional unset — the shape the ledger item's hosted `PipeImgGen` run
        produced. The second nulls the *defaulted* field explicitly, which a producer may do because the
        generated annotation is `X | None`: that is the payload a bare `.default(…)` rejects.
        """
        load_empty_library()
        registry = get_class_registry()
        classes: dict[str, Any] = {}
        for code, blueprint in _AUTHORED.items():
            concept = ConceptFactory.make_from_blueprint(domain_code=_DOMAIN, concept_code=code, blueprint_or_string_description=blueprint)
            classes[concept.structure_class_name] = registry.get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)
            classes[code] = classes[concept.structure_class_name]
        # A concept reference is generated as a quoted forward ref, so the classes need the same rebuild
        # against a shared namespace the library manager performs on load (`_rebuild_models_with_forward_refs`).
        for structure_class in dict.fromkeys(classes.values()):
            structure_class.model_rebuild(_types_namespace=classes)

        # `Detail` exists only to be referenced; `Payload` is the one that gets dumped.
        payload_class = classes["Payload"]
        return [
            payload_class(title="Everything optional left unset").model_dump(serialize_as_any=True),
            payload_class(title="A producer nulling the defaulted field", status=None).model_dump(serialize_as_any=True),
        ]

    def test_the_wire_carries_unset_optionals_as_explicit_nulls(self, wire_payloads: list[dict[str, Any]]):
        """The fact the projection has to accommodate — pinned here so it cannot change unnoticed."""
        unset, nulled_default = wire_payloads

        assert unset["title"] == "Everything optional left unset"
        for field_name in ("note", "detail", "tags", "counts"):
            assert field_name in unset, f"{field_name} was dropped from the transport dump"
            assert unset[field_name] is None, f"{field_name} is {unset[field_name]!r}, not the explicit null the wire carries"
        # A defaulted field is not nulled when unset — the default is applied — but it can be nulled explicitly.
        assert unset["status"] == "draft"
        assert nulled_default["status"] is None

    def test_every_non_required_field_projects_null_tolerant(self):
        """`.optional()` alone is `T | undefined` in zod, and would reject the payload pinned above."""
        content = emit_ts_zod(resolve_concepts_from_crate(normalize_crate(_authored_crate(), mthds_version=CRATE_TEST_VERSION)))[0].content

        assert ".optional()" not in content
        for field_name in _NON_REQUIRED_FIELDS:
            # Every field of this crate is short enough to stay on one line, so a missing match means the
            # field vanished from the projection rather than that it was broken across lines.
            line = next((line for line in content.splitlines() if line.strip().startswith(f"{field_name}: ")), None)
            assert line is not None, f"{field_name} has no field line in the emitted schema"
            assert ".nullish()" in line or ".nullable()" in line, f"{field_name} is not null-tolerant: {line.strip()}"
        # The nested concept's own optional field, reached through the reference rather than declared beside it.
        assert "weight: z.number().nullish()," in content

    def test_the_emitted_schema_parses_the_runtime_payload(self, wire_payloads: list[dict[str, Any]], tmp_path: Path):
        """The round trip itself: a real zod, the emitted schema, the runtime's own JSON.

        This is the only layer that executes the projection, so it is the one that would catch a schema
        that is well-formed and still wrong. `make test-ts-gates` provisions node's companions and sets
        `PIPELEX_REQUIRE_TS_GATES`, under which an absent toolchain fails here instead of skipping, and CI
        runs that target. Without the flag it still skips, and the two pins above encode the same contract.
        """
        node = resolve_node()
        zod_package = resolve_zod_package()

        content = emit_ts_zod(resolve_concepts_from_crate(normalize_crate(_authored_crate(), mthds_version=CRATE_TEST_VERSION)))[0].content
        (tmp_path / "types.ts").write_text(content, encoding="utf-8")
        (tmp_path / "package.json").write_text('{ "type": "module" }\n', encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "zod").symlink_to(zod_package, target_is_directory=True)
        (tmp_path / "wire.json").write_text(json.dumps(wire_payloads), encoding="utf-8")
        (tmp_path / "driver.ts").write_text(
            'import { readFileSync } from "node:fs";\n'
            'import { PayloadSchema } from "./types.ts";\n'
            'const wire = JSON.parse(readFileSync("wire.json", "utf-8"));\n'
            "process.stdout.write(JSON.stringify(wire.map((one: unknown) => PayloadSchema.parse(one))));\n",
            encoding="utf-8",
        )

        run = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [node, "--experimental-strip-types", "--no-warnings", "driver.ts"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, f"the emitted schema rejected the runtime's own payload:\n{run.stdout}\n{run.stderr}"

        unset, nulled_default = json.loads(run.stdout)
        # Nulls survive as nulls: the schema describes the wire, it does not fold `null` into `undefined`
        # (the binder uses one schema for both parse and serialize, so a transform would desynchronize them).
        for field_name in ("note", "detail", "tags", "counts"):
            assert unset[field_name] is None, f"{field_name} came back as {unset[field_name]!r} instead of null"
        assert unset["status"] == "draft"
        assert nulled_default["status"] is None
