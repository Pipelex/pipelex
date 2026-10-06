from typing import Any

import pytest

from pipelex.core.memory.exceptions import ExplicitConceptIncompatibleError
from pipelex.core.memory.input_shaper import InputKind, InputShaper
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import build_input_specs

_REPORT = "# Roof\n\n- two cracked tiles"


class TestMarkdownInputs:
    def test_markdown_takes_the_text_arm(self) -> None:
        """A declared Markdown input reads a string, as a Text input does."""
        library = get_concept_library()
        markdown = library.get_required_concept(concept_ref="native.Markdown")
        assert InputShaper.resolve_input_kind(markdown, concept_provider=library) == InputKind.TEXT

    @pytest.mark.parametrize(
        "provided",
        [
            _REPORT,
            {"concept": "Markdown", "content": _REPORT},
            {"concept": "native.Markdown", "content": _REPORT},
            {"concept": "Markdown", "content": {"text": _REPORT}},
        ],
    )
    def test_every_form_builds_markdown_content(self, provided: Any) -> None:
        """The bare string, the envelope with a string, and the envelope with the content form all hold a MarkdownContent."""
        input_specs = build_input_specs([("report", "native.Markdown", None)])

        working_memory = InputShaper.shape({"report": provided}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        stuff = working_memory.root["report"]
        assert stuff.concept.concept_ref == "native.Markdown"
        assert type(stuff.content) is MarkdownContent
        assert stuff.content == MarkdownContent(text=_REPORT)

    def test_markdown_envelope_fills_a_text_input(self) -> None:
        """A Markdown envelope is accepted where a Text is declared, and keeps being a Markdown."""
        input_specs = build_input_specs([("report", "native.Text", None)])
        provided = {"concept": "Markdown", "content": _REPORT}

        working_memory = InputShaper.shape({"report": provided}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        stuff = working_memory.root["report"]
        assert stuff.concept.concept_ref == "native.Markdown"
        assert stuff.content == MarkdownContent(text=_REPORT)

    @pytest.mark.parametrize("envelope_concept", ["Text", "shaper_test.Question"])
    def test_text_envelope_is_refused_for_a_markdown_input(self, envelope_concept: str) -> None:
        """A Text, or a concept refining Text, is not a Markdown: the envelope is refused rather than formatted."""
        input_specs = build_input_specs([("report", "native.Markdown", None)])
        provided = {"concept": envelope_concept, "content": _REPORT}

        with pytest.raises(ExplicitConceptIncompatibleError):
            InputShaper.shape({"report": provided}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

    def test_factory_envelope_with_a_list_of_strings(self) -> None:
        """The envelope form with a list of strings holds one MarkdownContent per item."""
        stuff = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data={"concept": "Markdown", "content": ["# One", "# Two"]},
            concept_provider=get_concept_library(),
            name="reports",
            read_scope=None,
        )
        assert stuff.concept.concept_ref == "native.Markdown"
        assert stuff.content == ListContent(items=[MarkdownContent(text="# One"), MarkdownContent(text="# Two")])

    def test_factory_infers_markdown_from_the_content_class(self) -> None:
        """A MarkdownContent handed over with no concept is a Markdown stuff, and a bare string a Text one."""
        library = get_concept_library()
        markdown_stuff = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data=MarkdownContent(text=_REPORT), concept_provider=library, name="report", read_scope=None
        )
        text_stuff = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data=_REPORT, concept_provider=library, name="note", read_scope=None
        )
        assert markdown_stuff.concept.concept_ref == "native.Markdown"
        assert text_stuff.concept.concept_ref == "native.Text"
        assert type(text_stuff.content) is TextContent
