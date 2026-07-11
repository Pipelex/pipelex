"""Unit tests for the light (signature-driven) inputs-template transform and its TOML serializer.

These cover the pure pieces of the D11 flip in isolation — no library, no concept resolution:

- ``_delighten_entry`` turns one envelope entry (``{"concept", "content"}``) into the light value
  the shaper accepts, dispatched on the input's already-resolved ``InputKind`` (a scalar unwraps to
  its bare field, a structured value keeps its content dict, a dynamic value keeps the whole
  envelope because bottom-up shaping still needs it).
- ``serialize_inputs_template_to_toml(..., light=True)`` lays a light template out with inline
  tables (so a bare scalar declared after a structured value stays at the top level and the document
  is valid TOML) and attaches ``# concept: ...`` comments.

The end-to-end path (real ``resolve_input_kind`` against a loaded bundle) is covered by the golden
integration test.
"""

from __future__ import annotations

from typing import Any

import tomli

from pipelex.core.memory.input_shaper import InputKind
from pipelex.core.pipes.inputs.input_renderer import (
    _delighten_entry,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    serialize_inputs_template_to_toml,
)


class TestInputRendererLight:
    def test_text_scalar_unwraps_to_bare_string(self) -> None:
        """A Text-refining input's ``{"text": ...}`` content becomes the bare string."""
        entry = {"concept": "demo.Question", "content": {"text": "text_value"}}
        assert _delighten_entry(entry, kind=InputKind.TEXT) == "text_value"

    def test_number_scalar_unwraps_to_bare_number(self) -> None:
        """A Number-refining input's ``{"number": ...}`` content becomes the bare number."""
        entry = {"concept": "demo.Priority", "content": {"number": 1}}
        assert _delighten_entry(entry, kind=InputKind.NUMBER) == 1

    def test_yes_no_scalar_unwraps_to_bare_bool(self) -> None:
        """A YesNo-refining input's ``{"yes_no": ...}`` content becomes the bare boolean."""
        entry = {"concept": "demo.Flag", "content": {"yes_no": False}}
        assert _delighten_entry(entry, kind=InputKind.YES_NO) is False

    def test_date_scalar_unwraps_to_bare_iso_string(self) -> None:
        """A Date-refining input's ``{"date": ...}`` content becomes the bare ISO string."""
        entry = {"concept": "demo.When", "content": {"date": "2026-01-01"}}
        assert _delighten_entry(entry, kind=InputKind.DATE) == "2026-01-01"

    def test_image_scalar_unwraps_to_bare_url(self) -> None:
        """An Image-refining input's ``{"url": ...}`` content becomes the bare URL string."""
        entry = {"concept": "demo.Photo", "content": {"url": "https://example.invalid/p.jpg"}}
        assert _delighten_entry(entry, kind=InputKind.IMAGE) == "https://example.invalid/p.jpg"

    def test_document_scalar_unwraps_to_bare_url(self) -> None:
        """A Document-refining input's ``{"url": ...}`` content becomes the bare URL string."""
        entry = {"concept": "demo.Exhibit", "content": {"url": "https://example.invalid/d.pdf"}}
        assert _delighten_entry(entry, kind=InputKind.DOCUMENT) == "https://example.invalid/d.pdf"

    def test_structured_keeps_content_dict(self) -> None:
        """A structured input keeps its content dict verbatim (no envelope, no unwrap)."""
        entry = {"concept": "demo.Invoice", "content": {"invoice_number": "INV-1", "amount": 0.0}}
        assert _delighten_entry(entry, kind=InputKind.STRUCTURED) == {"invoice_number": "INV-1", "amount": 0.0}

    def test_structured_multiple_keeps_list_of_dicts(self) -> None:
        """A structured list input keeps its ``[content]`` list verbatim."""
        entry: dict[str, Any] = {"concept": "demo.Person", "content": [{"name": "name_value", "job": "job_value"}]}
        assert _delighten_entry(entry, kind=InputKind.STRUCTURED) == [{"name": "name_value", "job": "job_value"}]

    def test_scalar_multiple_unwraps_element_wise(self) -> None:
        """A scalar list input unwraps every item to its bare field value."""
        entry: dict[str, Any] = {"concept": "demo.Tag", "content": [{"text": "t1"}, {"text": "t2"}]}
        assert _delighten_entry(entry, kind=InputKind.TEXT) == ["t1", "t2"]

    def test_scalar_empty_list_stays_empty(self) -> None:
        """A scalar list input with an empty content list stays an empty list."""
        entry: dict[str, Any] = {"concept": "demo.Tag", "content": []}
        assert _delighten_entry(entry, kind=InputKind.TEXT) == []

    def test_dynamic_keeps_the_whole_envelope(self) -> None:
        """A Dynamic/out-of-matrix input keeps the ceremonial envelope: bottom-up shaping needs it."""
        entry = {"concept": "native.Anything", "content": {"whatever": "value"}}
        assert _delighten_entry(entry, kind=InputKind.DYNAMIC) == entry

    def test_scalar_with_extra_required_fields_falls_back_to_envelope(self) -> None:
        """A scalar whose content is not a single field can't be delightened losslessly — keep the envelope."""
        entry = {"concept": "demo.Weird", "content": {"text": "t", "extra": "x"}}
        assert _delighten_entry(entry, kind=InputKind.TEXT) == entry

    def test_light_toml_round_trips_and_keeps_declaration_order(self) -> None:
        """A light template with a bare scalar declared AFTER a structured value stays valid TOML.

        The structured value is emitted as an inline table so the trailing scalar is not swallowed
        into a ``[section]`` — the whole document loads back equal to the light template.
        """
        template: dict[str, Any] = {
            "question": "text_value",
            "invoice": {"invoice_number": "INV-1", "amount": 0.0},
            "priority": 1,
            "tags": ["a", "b"],
            "people": [{"name": "name_value", "job": "job_value"}],
        }
        toml_str = serialize_inputs_template_to_toml(template, light=True)

        assert tomli.loads(toml_str) == template

    def test_light_toml_attaches_concept_comments(self) -> None:
        """Light TOML carries the declared concept as a ``# concept: ...`` comment above each key."""
        template: dict[str, Any] = {"question": "text_value", "invoice": {"invoice_number": "INV-1"}}
        comments = {"question": "concept: demo.Question", "invoice": "concept: demo.Invoice"}

        toml_str = serialize_inputs_template_to_toml(template, light=True, concept_comments=comments)

        assert "# concept: demo.Question" in toml_str
        assert "# concept: demo.Invoice" in toml_str
        assert tomli.loads(toml_str) == template

    def test_explicit_toml_default_keeps_section_layout(self) -> None:
        """Without light=True the serializer is unchanged: envelope entries render as sections and round-trip."""
        template: dict[str, Any] = {"question": {"concept": "demo.Question", "content": {"text": "text_value"}}}

        toml_str = serialize_inputs_template_to_toml(template)

        assert "[question]" in toml_str
        assert tomli.loads(toml_str) == template
