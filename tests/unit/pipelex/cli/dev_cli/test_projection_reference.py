"""The reference projection's rules, pinned one by one.

These are the rules the two shipped projections (the `mthds` TypeScript helper and its
`mthds-python` twin) must reproduce, and which the shared fixture corpus states as bytes. They are
asserted here against hand-built descriptors rather than against the corpus, so a rule that changed
fails by name instead of as a wall of differing bytes.

Four of them are deliberate departures from the engine's own renderer
(`pipelex/pipe_machinery/rendering/input_renderer.py`), each recorded in the corpus manifest the
generator writes; the rest is what the engine already does.

Descriptors are built here from plain dictionaries rather than from the model classes, because that
is the shape the shipped projections actually receive — the corpus files are JSON, and a rule that
only holds for a Python-constructed model would not be a rule the corpus can state.
"""

from typing import Any

import pytest

from pipelex.cli.dev_cli.commands.projection_reference import (
    project_concept_comments,
    project_inputs_template,
)
from pipelex.pipeline.input_form import PipeInputFormDescriptor


def _descriptor(*slots: dict[str, Any]) -> PipeInputFormDescriptor:
    """A descriptor holding the given slots, in order, each stamped with its pipe-slot facts.

    `presence` and `gating` are stated on a top-level field and forbidden below it, so they are
    added here rather than written out at every call site.
    """
    fields = [{**slot, "presence": "plain" if slot["required"] else "optional", "gating": bool(slot["required"])} for slot in slots]
    return PipeInputFormDescriptor.model_validate({"fields": fields})


def _text(*, name: str, required: bool = True) -> dict[str, Any]:
    """A nested text field — no pipe-slot facts, which the descriptor forbids below the top level."""
    return {"kind": "text", "name": name, "concept_ref": "native.Text", "required": required}


class TestDeliberateDivergencesFromTheEngine:
    """The four places the projection is right where the engine's renderer is not."""

    def test_a_text_field_merely_named_url_takes_a_text_placeholder(self):
        """The engine picks a placeholder by field name; the descriptor states the kind."""
        bookmark = {
            "kind": "object",
            "name": "bookmark",
            "concept_ref": "shelf.Bookmark",
            "required": True,
            "fields": [_text(name="url")],
        }
        template = project_inputs_template(descriptor=_descriptor(bookmark), explicit=False)
        assert template["bookmark"]["url"] == "url_value"
        assert "mock.invalid" not in template["bookmark"]["url"]

    def test_an_optional_structure_field_is_rendered(self):
        """The engine hides it at depth one, which is how the old template lost a file position."""
        dossier = {
            "kind": "object",
            "name": "dossier",
            "concept_ref": "shelf.Dossier",
            "required": True,
            "fields": [
                _text(name="title"),
                {"kind": "image", "name": "cover", "concept_ref": "native.Image", "required": False},
            ],
        }
        template = project_inputs_template(descriptor=_descriptor(dossier), explicit=False)
        assert set(template["dossier"]) == {"title", "cover"}

    def test_a_fixed_count_slot_renders_its_count(self):
        """`Concept[2]` needs two elements: `InputShaper` rejects a one-element scaffold outright."""
        pair = {
            "kind": "list",
            "name": "pair",
            "concept_ref": "shelf.Bookmark",
            "required": True,
            "item_count": 2,
            "item": {"kind": "object", "required": True, "fields": [_text(name="label")]},
        }
        template = project_inputs_template(descriptor=_descriptor(pair), explicit=False)
        assert len(template["pair"]) == 2
        assert template["pair"][0] == template["pair"][1] == {"label": "label_value"}

    def test_a_file_node_is_a_leaf_carrying_only_its_url(self):
        """The engine expands the runtime content class and asks for a width and a mime type."""
        dossier = {
            "kind": "object",
            "name": "dossier",
            "concept_ref": "shelf.Dossier",
            "required": True,
            "fields": [{"kind": "image", "name": "stamp", "concept_ref": "native.Image", "required": True}],
        }
        template = project_inputs_template(descriptor=_descriptor(dossier), explicit=False)
        assert template["dossier"]["stamp"] == {"url": "https://mock.invalid/url"}


class TestShapes:
    """Compact and explicit, and what separates them."""

    def test_a_variable_list_renders_one_example_element(self):
        many = {
            "kind": "list",
            "name": "many",
            "concept_ref": "native.Text",
            "required": True,
            "item": {"kind": "text", "required": True, "concept_ref": "native.Text"},
        }
        assert project_inputs_template(descriptor=_descriptor(many), explicit=False)["many"] == ["text_value"]

    def test_a_scalar_slot_unwraps_in_the_compact_shape_and_keeps_its_key_in_the_explicit_one(self):
        descriptor = _descriptor(_text(name="note"))
        assert project_inputs_template(descriptor=descriptor, explicit=False)["note"] == "text_value"
        assert project_inputs_template(descriptor=descriptor, explicit=True)["note"] == {
            "concept": "native.Text",
            "content": {"text": "text_value"},
        }

    def test_a_file_slot_unwraps_to_a_bare_url_in_the_compact_shape(self):
        cover = {"kind": "image", "name": "cover", "concept_ref": "native.Image", "required": True}
        assert project_inputs_template(descriptor=_descriptor(cover), explicit=False)["cover"] == "https://mock.invalid/url"

    def test_an_unknown_node_renders_as_an_empty_object(self):
        """The escape hatch's only honest value: the descriptor states nothing to render."""
        opaque = {"kind": "unknown", "name": "opaque", "concept_ref": "shelf.Opaque", "required": True}
        assert project_inputs_template(descriptor=_descriptor(opaque), explicit=False)["opaque"] == {}


class TestPlaceholdersByKind:
    """Every leaf kind's fill-in value, at a slot and inside a structure."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"kind": "text", "concept_ref": "native.Text"}, "text_value"),
            ({"kind": "text", "concept_ref": "native.Text", "format": "time"}, "12:00:00"),
            ({"kind": "prose", "concept_ref": "native.Text"}, "text_value"),
            ({"kind": "date", "concept_ref": "native.Date", "datetime": False}, "2026-01-01"),
            ({"kind": "date", "concept_ref": "native.Date", "datetime": True}, "2026-01-01T12:00:00"),
            ({"kind": "number", "concept_ref": "native.Number", "integer": False}, 1),
            ({"kind": "number", "integer": True}, 0),
            ({"kind": "number", "integer": False}, 0.0),
            ({"kind": "boolean", "concept_ref": "native.Boolean"}, False),
            ({"kind": "enum", "choices": ["draft", "final"]}, "draft"),
            ({"kind": "image", "concept_ref": "native.Image"}, "https://mock.invalid/url"),
            ({"kind": "document", "concept_ref": "native.Document"}, "https://mock.invalid/url"),
        ],
    )
    def test_a_leaf_slot_takes_its_kind_s_placeholder(self, node: dict[str, Any], expected: Any):
        slot = {**node, "name": "slot", "required": True}
        assert project_inputs_template(descriptor=_descriptor(slot), explicit=False)["slot"] == expected

    def test_an_enum_takes_its_first_choice_never_a_random_one(self):
        """The engine picks at random, which no committed template can carry."""
        slot = {"kind": "enum", "name": "status", "required": True, "choices": ["draft", "review", "final"]}
        descriptor = _descriptor(slot)
        renderings = {project_inputs_template(descriptor=descriptor, explicit=False)["status"] for _ in range(10)}
        assert renderings == {"draft"}


class TestOutOfMatrixNatives:
    """The natives the runtime's shaper cannot rebuild from a bare value keep their envelope."""

    @pytest.mark.parametrize("native_ref", ["native.Page", "native.Html", "native.TextAndImages"])
    def test_an_out_of_matrix_native_keeps_its_envelope_in_the_compact_shape(self, native_ref: str):
        slot = {
            "kind": "object",
            "name": "payload",
            "concept_ref": native_ref,
            "required": True,
            "fields": [_text(name="inner")],
        }
        projected = project_inputs_template(descriptor=_descriptor(slot), explicit=False)["payload"]
        assert projected == {"concept": native_ref, "content": {"inner": "inner_value"}}

    def test_a_concept_refining_an_out_of_matrix_native_keeps_it_too(self):
        """The identity is read off the whole chain, not off `concept_ref` alone."""
        slot = {
            "kind": "object",
            "name": "payload",
            "concept_ref": "shelf.Rendered",
            "refines": ["native.Html"],
            "required": True,
            "fields": [_text(name="inner")],
        }
        projected = project_inputs_template(descriptor=_descriptor(slot), explicit=False)["payload"]
        assert projected == {"concept": "shelf.Rendered", "content": {"inner": "inner_value"}}

    def test_an_ordinary_structured_concept_unwraps_to_its_content_dict(self):
        slot = {
            "kind": "object",
            "name": "review",
            "concept_ref": "shelf.Review",
            "required": True,
            "fields": [_text(name="inner")],
        }
        assert project_inputs_template(descriptor=_descriptor(slot), explicit=False)["review"] == {"inner": "inner_value"}


class TestConceptComments:
    """The `# concept: …` line a light TOML rendering carries, rebuilt from the descriptor alone."""

    def test_a_plain_slot_states_its_concept(self):
        assert project_concept_comments(descriptor=_descriptor(_text(name="note"))) == {"note": "concept: native.Text"}

    def test_a_fixed_count_slot_states_its_count(self):
        pair = {
            "kind": "list",
            "name": "pair",
            "concept_ref": "shelf.Bookmark",
            "required": True,
            "item_count": 2,
            "item": {"kind": "text", "required": True},
        }
        assert project_concept_comments(descriptor=_descriptor(pair)) == {"pair": "concept: shelf.Bookmark[2]"}

    def test_an_optional_variable_slot_states_both_markers(self):
        many = {
            "kind": "list",
            "name": "many",
            "concept_ref": "shelf.Bookmark",
            "required": False,
            "item": {"kind": "text", "required": True},
        }
        assert project_concept_comments(descriptor=_descriptor(many)) == {"many": "concept: shelf.Bookmark[]?"}
