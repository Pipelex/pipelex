"""Unit tests for the inputs-template TOML serializer (serialize_inputs_template_to_toml)."""

from __future__ import annotations

import tomli

from pipelex.core.pipes.rendering.input_renderer import serialize_inputs_template_to_toml


class TestSerializeInputsTemplateToml:
    def test_representative_template_round_trips(self) -> None:
        """A template shaped like the generator's output survives a TOML dump/parse unchanged."""
        template = {
            "document": {
                "concept": "demo.Document",
                "content": {
                    "url": "https://example.invalid/doc",
                    "page_count": 0,
                    "score": 0.0,
                    "is_signed": False,
                    "tags": ["tags_item"],
                    "metadata": {"metadata_key": "metadata_value"},
                },
            },
            "people": {
                "concept": "demo.Person",
                "content": [{"name": "name_value", "age": 0}],
            },
        }

        toml_str = serialize_inputs_template_to_toml(template)

        assert tomli.loads(toml_str) == template

    def test_multiline_string_round_trips(self) -> None:
        """Multi-line string placeholders survive the TOML round trip byte-for-byte."""
        template = {"note": {"concept": "demo.Note", "content": {"text": "line one\nline two\n\nline four"}}}

        toml_str = serialize_inputs_template_to_toml(template)

        assert tomli.loads(toml_str) == template

    def test_none_values_become_empty_strings(self) -> None:
        """The pinned policy: TOML has no null, so None placeholders become empty strings — keys stay visible."""
        template = {
            "record": {
                "concept": "demo.Record",
                "content": {
                    "maybe_text": None,
                    "nested": {"maybe_inner": None},
                    "items": [None, "kept"],
                },
            },
        }

        loaded = tomli.loads(serialize_inputs_template_to_toml(template))

        assert loaded["record"]["content"]["maybe_text"] == ""
        assert loaded["record"]["content"]["nested"]["maybe_inner"] == ""
        assert loaded["record"]["content"]["items"] == ["", "kept"]

    def test_empty_template_serializes_to_empty_document(self) -> None:
        """An empty template is a valid, empty TOML document."""
        toml_str = serialize_inputs_template_to_toml({})

        assert tomli.loads(toml_str) == {}
