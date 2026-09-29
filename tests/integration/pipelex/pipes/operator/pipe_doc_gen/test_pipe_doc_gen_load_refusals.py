import pytest

from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import refusal_report
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenLoadRefusals:
    @pytest.mark.parametrize(
        "step_fields",
        [
            'format = "pdf"\ntemplate = "<h1>{{ invoice.number }}</h1>"',
            'format = "xlsx"',
        ],
        ids=["pdf_with_an_html_template", "xlsx_auto_layout"],
    )
    async def test_a_step_no_installed_engine_prints_names_the_plugin(self, step_fields: str) -> None:
        """Open Pipelex prints a pdf without a template only: any other step is refused at load, naming the plugin that prints it."""
        report = await refusal_report(step_fields=step_fields)
        assert "pipelex-doc-gen" in report

    @pytest.mark.usefixtures("no_engines")
    async def test_a_pdf_layout_step_is_refused_where_the_built_in_engine_is_disabled(self) -> None:
        """A host that disables the built-in engine and installs no plugin refuses even a pdf without a template."""
        report = await refusal_report(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)
        assert "built-in" in report

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_template_file_in_a_bundle_loaded_from_a_string_is_refused(self) -> None:
        """A bundle loaded from a string has no directory to find a template file in."""
        report = await refusal_report(step_fields='format = "docx"\ntemplate_file = "invoice.docx"')
        assert "not loaded from a file on disk" in report

    @pytest.mark.usefixtures("stub_engines")
    @pytest.mark.parametrize(
        ("step_fields", "expected"),
        [
            ('format = "pdf"\ntemplate = "<h1>{{ invoice.numbr }}</h1>"', "numbr"),
            ('format = "pdf"\ntemplate = "{% for line in invoice.line_items %}{{ line.amout }}{% endfor %}"', "amout"),
            ('format = "pdf"\nfilename = "invoice-{{ invoice.nmber }}"', "nmber"),
            ('format = "pdf"\ntemplate = "<h1>{{ invoice._stuff }}</h1>"', "_stuff"),
        ],
        ids=["misspelled_field", "misspelled_field_through_a_loop", "misspelled_field_in_the_filename", "private_name"],
    )
    async def test_a_template_mistake_is_refused_at_load(self, step_fields: str, expected: str) -> None:
        """A field a template or the filename names is checked against the input's concept, through loop variables too."""
        report = await refusal_report(step_fields=step_fields)
        assert expected in report

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_misspelling_the_load_check_cannot_follow_fails_at_the_dry_run(self) -> None:
        """A field read through a `set` alias escapes the load check, and the strict undefined names it at the dry run."""
        report = await refusal_report(step_fields='format = "pdf"\ntemplate = "{% set buyer = invoice %}<h1>{{ buyer.custmer }}</h1>"')
        assert "custmer" in report
        assert "could not render its template" in report
