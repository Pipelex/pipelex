import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.libraries.library_crate import LibraryCrate
from tests.helpers.ts_toolchain import resolve_node, resolve_zod_package
from tests.unit.pipelex.codegen.conftest import load_generated_module

_STORED_TEXT_URL = "pipelex-storage://org-1/run-1/generated/0123456789abcdef/value.txt"
_STORED_HTML_URL = "pipelex-storage://org-1/run-1/generated/fedcba9876543210/value.html"

# The concepts whose wire shape differs from their loaded shape: the natives that may hold their value in storage,
# and every concept reaching one through a field, a list item or a refinement. `Score` reaches none, and neither
# does `ReportWire`, whose code only looks like a wire shape's name.
_WIRE_SHAPED_REFS = {
    "native.Html",
    "native.JSON",
    "native.Markdown",
    "native.Page",
    "native.Text",
    "native.TextAndImages",
    "stored.Notes",
    "stored.Report",
    "stored.Summary",
}


def _stored_text_dump() -> dict[str, Any]:
    """What the runtime puts on the wire for a text it stored: the reference, no value."""
    content = TextContent(text="The full text of a page")
    content.accept_storage(url=_STORED_TEXT_URL, size=23, mime_type="text/plain", preview="The full text")
    return content.model_dump(serialize_as_any=True)


def _stored_html_dump() -> dict[str, Any]:
    content = HtmlContent(inner_html="<p>The page</p>", css_class="page")
    content.accept_storage(url=_STORED_HTML_URL, size=15, mime_type="text/html", preview="<p>The page")
    return content.model_dump(serialize_as_any=True)


class TestStoredValueShapes:
    """A text, HTML or JSON value the runtime stored travels as its reference, so codegen emits two shapes.

    The loaded shape (`Text`, `text: str`) is what a client hands its caller once it has loaded every stored value,
    and the wire shape (`TextWire`) is what the wire carries, either form of the value. A concept reaching a
    storable native gets both; a concept reaching none keeps its one shape.
    """

    def test_the_wire_shapes_cover_exactly_the_concepts_reaching_a_storable_native(self, stored_values_crate: LibraryCrate):
        library = resolve_concepts_from_crate(stored_values_crate)
        assert {twin.wire_shape_of for twin in library.wire_shapes} == _WIRE_SHAPED_REFS
        loaded_text = library.by_ref()["native.Text"]
        assert [(field.name, field.required) for field in loaded_text.fields] == [("text", True)]
        loaded_html = library.by_ref()["native.Html"]
        assert [(field.name, field.required) for field in loaded_html.fields] == [("inner_html", True), ("css_class", False)]
        wire_text = next(twin for twin in library.wire_shapes if twin.wire_shape_of == "native.Text")
        assert [(field.name, field.required) for field in wire_text.fields] == [
            ("text", False),
            ("url", False),
            ("size", False),
            ("mime_type", False),
            ("preview", False),
        ]

    def test_python_pydantic_emits_the_loaded_shape_and_the_wire_shape(self, stored_values_crate: LibraryCrate, tmp_path: Path):
        content = emit_python_pydantic(resolve_concepts_from_crate(stored_values_crate))[0].content
        assert 'text: str = Field(..., description="The text")' in content
        assert "class TextWire(BaseModel):" in content
        assert "class Summary(Text):" in content
        assert "class SummaryWire(TextWire):" in content
        assert "class ScoreWire" not in content
        # The authored `ReportWire` keeps its name, so `Report`'s wire shape takes the next free one.
        assert "class ReportWire(BaseModel):" in content
        assert "class ReportWire2(BaseModel):" in content

        module = load_generated_module(content, tmp_path=tmp_path, name="gen_models_stored_values")
        stored_text = _stored_text_dump()
        with pytest.raises(ValidationError):
            module.Text.model_validate(stored_text)
        wire_text = module.TextWire.model_validate(stored_text)
        assert wire_text.url == _STORED_TEXT_URL
        assert wire_text.text is None
        assert module.Text.model_validate({"text": "inline"}).text == "inline"
        assert module.TextWire.model_validate({"text": "inline"}).text == "inline"

        report_wire = {"label": stored_text, "body": _stored_html_dump(), "data": {"json_obj": {"k": 1}}, "score": {"value": 2.0}}
        parsed_wire = module.ReportWire2.model_validate(report_wire)
        assert parsed_wire.body.url == _STORED_HTML_URL
        assert parsed_wire.body.css_class == "page"
        assert parsed_wire.score.value == 2.0
        with pytest.raises(ValidationError):
            module.Report.model_validate(report_wire)
        loaded_report = {"label": {"text": "x"}, "body": {"inner_html": "<p>x</p>"}, "data": {"json_obj": {"k": 1}}}
        assert module.Report.model_validate(loaded_report).body.inner_html == "<p>x</p>"

    def test_ts_zod_emits_the_loaded_shape_and_the_wire_shape(self, stored_values_crate: LibraryCrate):
        types_file, binder_file = emit_ts_zod(resolve_concepts_from_crate(stored_values_crate))
        types_ts = types_file.content
        assert "export const TextSchema = z.object({\n  /** The text */\n  text: z.string(),\n});" in types_ts
        assert "export const TextWireSchema = z.object({" in types_ts
        assert "export const SummaryWireSchema = z.lazy(() => TextWireSchema);" in types_ts
        assert "export const ReportWire2Schema = z.object({" in types_ts
        assert "label: z.lazy(() => TextWireSchema).nullish()," in types_ts
        assert "score: z.lazy(() => ScoreSchema).nullish()," in types_ts
        assert "ScoreWire" not in types_ts
        assert "export function parseTextWire(wire: unknown): TextWire {" in binder_file.content
        assert "export function parseReportWire2(wire: unknown): ReportWire2 {" in binder_file.content

    def test_python_structures_keeps_the_runtime_classes_which_hold_both_forms(self, stored_values_crate: LibraryCrate):
        content = emit_python_structures(resolve_concepts_from_crate(stored_values_crate))[0].content
        assert "Wire2" not in content
        assert "class Summary(TextContent):" in content

    def test_the_emitted_zod_schemas_parse_the_runtime_payloads(self, stored_values_crate: LibraryCrate, tmp_path: Path):
        """A real zod: the wire shape takes a stored value and an inline one, the loaded shape refuses the stored one."""
        node = resolve_node()
        zod_package = resolve_zod_package()

        types_ts = emit_ts_zod(resolve_concepts_from_crate(stored_values_crate))[0].content
        stored_json = JSONContent(json_obj={"answer": 42})
        stored_json.accept_storage(
            url="pipelex-storage://org-1/run-1/generated/00ff00ff00ff00ff/value.json", size=14, mime_type="application/json", preview='{"answer": 42}'
        )
        payloads = {
            "stored_text": _stored_text_dump(),
            "inline_text": TextContent(text="inline").model_dump(serialize_as_any=True),
            "stored_html": _stored_html_dump(),
            "stored_json": stored_json.model_dump(serialize_as_any=True),
        }
        (tmp_path / "types.ts").write_text(types_ts, encoding="utf-8")
        (tmp_path / "package.json").write_text('{ "type": "module" }\n', encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "zod").symlink_to(zod_package, target_is_directory=True)
        (tmp_path / "wire.json").write_text(json.dumps(payloads), encoding="utf-8")
        (tmp_path / "driver.ts").write_text(
            'import { readFileSync } from "node:fs";\n'
            'import { TextSchema, TextWireSchema, HtmlWireSchema, JSONSchema, JSONWireSchema } from "./types.ts";\n'
            'const wire = JSON.parse(readFileSync("wire.json", "utf-8"));\n'
            "process.stdout.write(JSON.stringify({\n"
            "  storedTextWire: TextWireSchema.parse(wire.stored_text),\n"
            "  inlineTextWire: TextWireSchema.parse(wire.inline_text),\n"
            "  inlineTextLoaded: TextSchema.parse(wire.inline_text),\n"
            "  storedTextLoaded: TextSchema.safeParse(wire.stored_text).success,\n"
            "  storedHtmlWire: HtmlWireSchema.parse(wire.stored_html),\n"
            "  storedJsonWire: JSONWireSchema.parse(wire.stored_json),\n"
            "  storedJsonLoaded: JSONSchema.safeParse(wire.stored_json).success,\n"
            "}));\n",
            encoding="utf-8",
        )
        run = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [node, "--experimental-strip-types", "--no-warnings", "driver.ts"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, f"the emitted schemas rejected the runtime's own payload:\n{run.stdout}\n{run.stderr}"
        result = json.loads(run.stdout)
        assert result["storedTextWire"] == payloads["stored_text"]
        assert result["inlineTextWire"] == {"text": "inline"}
        assert result["inlineTextLoaded"] == {"text": "inline"}
        assert result["storedTextLoaded"] is False
        assert result["storedHtmlWire"] == payloads["stored_html"]
        assert result["storedJsonWire"]["url"].endswith("value.json")
        assert result["storedJsonLoaded"] is False
