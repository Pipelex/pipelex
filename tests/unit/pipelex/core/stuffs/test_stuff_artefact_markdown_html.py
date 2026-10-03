import pytest
from markupsafe import escape

from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.compose_ops import run_compose_template
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSecurityError
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_REPORT_SOURCE = "# Title\n\nFish & chips"
_REPORT_HTML = "<h1>Title</h1>\n<p>Fish &amp; chips</p>\n"
_REPORT_SOURCE_ESCAPED = "# Title\n\nFish &amp; chips"
_NOTE_SOURCE = "<b>Fish</b> & chips"
_NOTE_ESCAPED = "&lt;b&gt;Fish&lt;/b&gt; &amp; chips"
_TEMPLATING_STYLE = TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.PLAIN)


class InspectionDigest(StructuredContent):
    title: str
    summary: MarkdownContent


def _make_stuff(*, content: StuffContent, name: str, concept_code: NativeConceptCode) -> Stuff:
    return Stuff(
        stuff_code=f"{name}_code",
        stuff_name=name,
        concept=ConceptFactory.make_native_concept(native_concept_code=concept_code),
        content=content,
    )


def _make_report_artefact() -> StuffArtefact:
    return StuffArtefact(_make_stuff(content=MarkdownContent(text=_REPORT_SOURCE), name="report", concept_code=NativeConceptCode.MARKDOWN))


def _make_note_artefact() -> StuffArtefact:
    return StuffArtefact(_make_stuff(content=TextContent(text=_NOTE_SOURCE), name="note", concept_code=NativeConceptCode.TEXT))


@pytest.mark.asyncio(loop_scope="class")
class TestStuffArtefactMarkdownHtml:
    async def test_compose_html_template_converts_markdown_and_escapes_text(self):
        """In a PipeCompose HTML template, `{{ report }}` is the converted Markdown, `{{ note }}` the escaped Text."""
        memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                _make_stuff(content=MarkdownContent(text=_REPORT_SOURCE), name="report", concept_code=NativeConceptCode.MARKDOWN),
                _make_stuff(content=TextContent(text=_NOTE_SOURCE), name="note", concept_code=NativeConceptCode.TEXT),
            ]
        )
        compose_result = await run_compose_template(
            memory=memory,
            template="<section>{{ report }}</section><aside>{{ note }}</aside>",
            category=TemplateCategory.HTML,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.HTML),
            output_class=HtmlContent,
            templating_style=_TEMPLATING_STYLE,
            result_name="page",
        )
        assert compose_result.rendered_text == f"<section>{_REPORT_HTML}</section><aside>{_NOTE_ESCAPED}</aside>"

    @pytest.mark.parametrize(
        ("template_source", "expected"),
        [
            # The field is a plain string: escaped like any string.
            ("{{ report.text }}", _REPORT_SOURCE_ESCAPED),
            # markupsafe's escape and Markup both honour `__html__`.
            ("{{ report|e }}", _REPORT_HTML),
            ("{{ report|safe }}", _REPORT_HTML),
            # A Text stuff marked safe is inserted raw, as it always was: no `__html__` answers for it.
            ("{{ note|safe }}", _NOTE_SOURCE),
        ],
    )
    async def test_html_template_forms(self, template_source: str, expected: str):
        """What each spelling prints in an HTML template, for a Markdown and a Text stuff."""
        rendered = await render_jinja2_async(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={"report": _make_report_artefact(), "note": _make_note_artefact()},
        )
        assert rendered == expected

    @pytest.mark.parametrize(
        ("template_source", "expected"),
        [
            ("$report", _REPORT_HTML),
            ("{{ report|format }}", _REPORT_HTML),
            ("{{ report|format('html') }}", _REPORT_HTML),
            # A format the template names wins: plain is the source, which the template escapes.
            ("{{ report|format('plain') }}", _REPORT_SOURCE_ESCAPED),
            ("$note", _NOTE_ESCAPED),
        ],
        ids=["sigil", "format_filter", "format_filter_naming_html", "format_filter_naming_plain", "text_sigil"],
    )
    async def test_the_format_filter_prints_markdown_as_html(self, template_source: str, expected: str):
        """In an HTML template, `$report` and `{{ report|format }}` print what `{{ report }}` prints, and a Text stays escaped."""
        rendered = await render_jinja2_async(
            template_source=preprocess_template(template_source),
            template_category=TemplateCategory.HTML,
            templating_context={"report": _make_report_artefact(), "note": _make_note_artefact()},
            templating_style=_TEMPLATING_STYLE,
        )
        assert rendered == expected

    async def test_markdown_field_of_a_structure_converts(self):
        """A Markdown value one field down, `{{ digest.summary }}`, converts too: the content itself answers `__html__`."""
        digest = InspectionDigest(title="Roof & gutters", summary=MarkdownContent(text=_REPORT_SOURCE))
        artefact = StuffArtefact(
            Stuff(
                stuff_code="digest_code",
                stuff_name="digest",
                concept=ConceptFactory.make(
                    concept_code="InspectionDigest",
                    domain_code="inspections",
                    description="A digest",
                    structure_class_name="InspectionDigest",
                ),
                content=digest,
            )
        )
        rendered = await render_jinja2_async(
            template_source="<h2>{{ digest.title }}</h2>{{ digest.summary }}",
            template_category=TemplateCategory.HTML,
            templating_context={"digest": artefact},
        )
        assert rendered == f"<h2>Roof &amp; gutters</h2>{_REPORT_HTML}"

    @pytest.mark.parametrize("template_category", [TemplateCategory.MARKDOWN, TemplateCategory.LLM_PROMPT, TemplateCategory.BASIC])
    async def test_without_autoescape_markdown_prints_its_source(self, template_category: TemplateCategory):
        """Where nothing is escaped (a prompt, a Markdown template), a Markdown stuff prints its source as it is."""
        rendered = await render_jinja2_async(
            template_source="{{ report }}",
            template_category=template_category,
            templating_context={"report": _make_report_artefact()},
        )
        assert rendered == _REPORT_SOURCE

    async def test_template_cannot_call_html_dunder(self):
        """The sandbox refuses `__html__` from a template: only markupsafe calls it, when it escapes."""
        with pytest.raises(Jinja2TemplateSecurityError):
            await render_jinja2_async(
                template_source="{{ report.__html__() }}",
                template_category=TemplateCategory.HTML,
                templating_context={"report": _make_report_artefact()},
            )

    async def test_only_a_content_that_knows_its_html_answers_html_dunder(self):
        """The artefact answers `__html__` for a Markdown content only, so every other stuff escapes as before."""
        report_artefact = _make_report_artefact()
        assert hasattr(report_artefact, "__html__")
        assert str(escape(report_artefact)) == _REPORT_HTML
        assert str(escape(_make_note_artefact())) == _NOTE_ESCAPED
        assert not hasattr(_make_note_artefact(), "__html__")
