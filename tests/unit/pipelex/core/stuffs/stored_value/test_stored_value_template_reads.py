from typing import Any

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.exceptions import StoredValueNotLoadedError
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat
from tests.unit.pipelex.core.stuffs.stored_value.test_data import STORED_HTML, STORED_TEXT, TEXT_URL, StoredValueTestData


class StoredValueReport(StructuredContent):
    """A structure holding stored values below its top level, where a template reaches them through attribute reads."""

    title: str
    body: TextContent
    page: HtmlContent


def _report_artefact(*, loaded: bool) -> StuffArtefact:
    body = TextContent.model_validate(StoredValueTestData.TEXT_REFERENCE)
    page = HtmlContent.model_validate(StoredValueTestData.HTML_REFERENCE)
    if loaded:
        body.accept_loaded_text(text=STORED_TEXT)
        page.accept_loaded_text(text=STORED_HTML)
    report = StoredValueReport(title="Quarterly", body=body, page=page)
    concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
    return StuffArtefact(Stuff(stuff_code="report_code", stuff_name="report", concept=concept, content=report))


async def _render(*, template_source: str, context: dict[str, Any]) -> str:
    return await render_jinja2_async(
        template_category=TemplateCategory.LLM_PROMPT,
        templating_context=context,
        template_source=template_source,
        templating_style=TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestStoredValueTemplateReads:
    @pytest.mark.parametrize(
        "template_source",
        [
            "Body: {{ report.body.text }}",
            "Body: {{ report.body['text'] }}",
            "Page: {{ report.page.inner_html }}",
            "Page: {{ report.page['inner_html'] }}",
        ],
    )
    async def test_reading_the_value_field_of_a_nested_reference_never_loaded_raises(self, template_source: str):
        """A template reading the value field of a stored value below the top level refuses, as one reading it at the top does."""
        with pytest.raises(StoredValueNotLoadedError):
            await _render(template_source=template_source, context={"report": _report_artefact(loaded=False)})

    @pytest.mark.parametrize(
        ("template_source", "expected"),
        [
            ("{{ report.body.text }}", STORED_TEXT),
            ("{{ report.body['text'] }}", STORED_TEXT),
            ("{{ report.page.inner_html }}", STORED_HTML),
        ],
    )
    async def test_reading_the_value_field_of_a_nested_loaded_reference_renders_the_value(self, template_source: str, expected: str):
        rendered = await _render(template_source=template_source, context={"report": _report_artefact(loaded=True)})

        assert rendered == expected

    async def test_reading_the_reference_of_a_nested_stored_value_still_reads_it(self):
        """Only the value field is guarded: the reference and its description stay readable without a load."""
        rendered = await _render(template_source="{{ report.body.url }}", context={"report": _report_artefact(loaded=False)})

        assert rendered == TEXT_URL
