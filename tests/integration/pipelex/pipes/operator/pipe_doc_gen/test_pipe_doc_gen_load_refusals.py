import pytest

from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import refusal_report
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenLoadRefusals:
    @pytest.mark.parametrize(
        ("step_fields", "asks"),
        [
            ('format = "pdf"\ntemplate = "<h1>{{ invoice.number }}</h1>"', "a pdf from an HTML template"),
            ('format = "xlsx"', "an xlsx from the auto-layout of its inputs"),
        ],
        ids=["pdf_with_an_html_template", "xlsx_auto_layout"],
    )
    async def test_a_step_no_installed_engine_prints_names_the_plugin(self, step_fields: str, asks: str) -> None:
        """Open Pipelex declares a default for a pdf without a template only: any other step is refused at load, naming the plugin."""
        report = await refusal_report(step_fields=step_fields)
        assert asks in report
        assert "pipelex-doc-gen" in report
        assert "pipelex update" not in report

    async def test_a_step_naming_a_plugin_engine_is_refused_where_the_plugin_is_absent(self) -> None:
        """A step may name the plugin's `pipelex-pdf` for a pdf without a template, and open Pipelex refuses it at load, naming the plugin."""
        report = await refusal_report(step_fields='format = "pdf"\nmodel = "pipelex-pdf"')
        assert "pipelex-pdf" in report
        assert "pipelex-doc-gen" in report
        assert "was not found in the model deck" not in report

    @pytest.mark.usefixtures("stale_internal_backend")
    @pytest.mark.parametrize(
        "step_fields",
        [PipeDocGenTestData.PDF_LAYOUT_STEP, 'format = "pdf"\nmodel = "reportlab-pdf"'],
        ids=["through_the_default", "named_by_the_step"],
    )
    async def test_a_pdf_layout_step_is_refused_where_internal_toml_predates_the_built_in_engine(self, step_fields: str) -> None:
        """An installation whose internal.toml does not declare `reportlab-pdf` is told to run `pipelex update`, not that the model is unknown."""
        report = await refusal_report(step_fields=step_fields)
        assert "reportlab-pdf" in report
        assert "pipelex update" in report
        assert "was not found in the model deck" not in report

    async def test_an_engine_that_does_not_print_the_step_s_source_is_refused(self) -> None:
        """ReportLab prints only the auto-layout, so a step that names it with an HTML template is refused at load."""
        report = await refusal_report(step_fields='format = "pdf"\nmodel = "reportlab-pdf"\ntemplate = "<h1>{{ invoice.number }}</h1>"')
        assert "reportlab-pdf" in report
        assert "from an HTML template, which it does not print" in report

    async def test_an_engine_the_deck_does_not_define_is_an_unknown_model(self) -> None:
        """A misspelled engine is refused at load like any unknown model, located on the step's `model` field."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\nmodel = "reportlab-pfd"')])
        report = str(exc_info.value.to_error_report().model_dump())
        assert "reportlab-pfd" in report
        assert "model" in report

    @pytest.mark.usefixtures("no_engines")
    async def test_a_pdf_layout_step_is_refused_where_the_built_in_engine_is_disabled(self) -> None:
        """A host that disables the built-in engine and installs no plugin refuses even a pdf without a template."""
        report = await refusal_report(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)
        assert "built into Pipelex and disabled" in report

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
    async def test_a_field_read_on_an_anything_input_is_left_to_the_dry_run(self) -> None:
        """An `Anything` input declares no fields for the load check to follow, so a field read on it is checked when the template renders."""
        bundle = PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate = "<h1>{{ invoice.number }} {{ thing.title }}</h1>"').replace(
            'inputs      = { invoice = "Invoice" }', 'inputs      = { invoice = "Invoice", thing = "Anything" }'
        )
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle])
        report = str(exc_info.value.to_error_report().model_dump())
        assert "could not render its template" in report
        assert "title" in report
        assert "AnythingContent" not in report

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_misspelling_the_load_check_cannot_follow_fails_at_the_dry_run(self) -> None:
        """A field read through a `set` alias escapes the load check, and the strict undefined names it at the dry run."""
        report = await refusal_report(step_fields='format = "pdf"\ntemplate = "{% set buyer = invoice %}<h1>{{ buyer.custmer }}</h1>"')
        assert "custmer" in report
        assert "could not render its template" in report

    @pytest.mark.parametrize(
        "filename",
        ["invoice-{{ reference }}", "invoice-$reference"],
        ids=["jinja2", "sigil"],
    )
    async def test_a_filename_reading_an_optional_input_unguarded_is_refused(self, filename: str) -> None:
        """The filename renders strictly, so an optional input it reads without a guard would fail every run that leaves it out."""
        bundle = PipeDocGenTestData.bundle(step_fields=f'format = "pdf"\nfilename = "{filename}"').replace(
            'inputs      = { invoice = "Invoice" }', 'inputs      = { invoice = "Invoice", reference = "Text?" }'
        )
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle])
        report = str(exc_info.value.to_error_report().model_dump())
        assert "reference" in report
        assert "filename" in report
