from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.core.bundle_resources.bundle_resource import BundleResourceReadStage
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint


def _blueprint(**overrides: Any) -> PipeDocGenBlueprint:
    kwargs: dict[str, Any] = {"description": "Print the invoice", "inputs": {"invoice": "Invoice"}, "output": "Document", "format": "pdf"}
    kwargs.update(overrides)
    return PipeDocGenBlueprint.model_validate(kwargs)


class TestPipeDocGenBlueprint:
    def test_a_pdf_without_a_template_is_the_auto_layout(self) -> None:
        blueprint = _blueprint(filename="invoice-{{ invoice.number }}")
        assert blueprint.format == DocGenFormat.PDF
        assert blueprint.template is None
        assert blueprint.template_file is None

    @pytest.mark.parametrize(
        ("topic", "overrides", "expected_message"),
        [
            ("both_templates", {"template": "<p>{{ invoice.number }}</p>", "template_file": "invoice.html"}, "both 'template' and 'template_file'"),
            ("inline_template_for_xlsx", {"format": "xlsx", "template": "<p>{{ invoice.number }}</p>"}, "for the 'pdf' format only"),
            ("wrong_template_suffix", {"format": "docx", "template_file": "invoice.xlsx"}, "must be a .docx file"),
            ("pptx_without_template", {"format": "pptx"}, "has no auto-layout"),
            ("unknown_format", {"format": "odt"}, "format"),
            ("template_reads_an_undeclared_input", {"template": "<p>{{ customer.name }}</p>"}, "Variable 'customer'"),
            ("filename_reads_an_undeclared_input", {"filename": "invoice-{{ order.number }}"}, "Variable 'order'"),
            ("list_output", {"output": "Document[]"}, "produces one file"),
            ("broken_template", {"template": "{% for %}"}, "Could not parse"),
            ("posix_absolute_template_file", {"format": "docx", "template_file": "/srv/methods/invoice.docx"}, "relative to the bundle's file"),
            ("windows_rooted_template_file", {"format": "docx", "template_file": "\\methods\\invoice.docx"}, "relative to the bundle's file"),
            ("drive_absolute_template_file", {"format": "docx", "template_file": "C:/methods/invoice.docx"}, "relative to the bundle's file"),
            ("drive_relative_template_file", {"format": "docx", "template_file": "C:invoice.docx"}, "relative to the bundle's file"),
            ("unc_template_file", {"format": "docx", "template_file": "\\\\server\\share\\invoice.docx"}, "relative to the bundle's file"),
        ],
    )
    def test_refused_blueprints(
        self,
        topic: str,  # ruff: ignore[unused-method-argument]
        overrides: dict[str, Any],
        expected_message: str,
    ) -> None:
        with pytest.raises(ValidationError, match=expected_message):
            _blueprint(**overrides)

    @pytest.mark.parametrize("template_file", ["invoice.docx", "./invoice.docx", "templates/invoice.docx", "templates/../invoice.docx"])
    def test_a_relative_template_file_is_accepted(self, template_file: str) -> None:
        blueprint = _blueprint(format="docx", template_file=template_file)
        assert blueprint.template_file == template_file

    def test_the_refusal_of_an_absolute_template_file_never_repeats_it(self) -> None:
        """A host library's step would otherwise put the host's own path in front of a caller."""
        with pytest.raises(ValidationError) as exc_info:
            _blueprint(format="docx", template_file="/srv/methods/invoice.docx")
        assert all("/srv/methods" not in error["msg"] for error in exc_info.value.errors())

    def test_a_name_every_branch_sets_is_the_template_s_own(self) -> None:
        template = (
            "{% if invoice.paid %}{% set status = 'Paid' %}{% else %}{% set status = 'Due' %}{% endif %}<h1>{{ invoice.number }}: {{ status }}</h1>"
        )
        blueprint = _blueprint(template=template)
        assert blueprint.template == template

    def test_a_sigil_in_the_template_reads_its_input(self) -> None:
        blueprint = _blueprint(template="<h1>$invoice.number</h1>")
        assert blueprint.template == "<h1>$invoice.number</h1>"

    @pytest.mark.parametrize(
        ("overrides", "expected_reads"),
        [
            ({"template_file": "templates/invoice.html"}, {"templates/invoice.html": BundleResourceReadStage.LOAD}),
            ({"format": "docx", "template_file": "invoice.docx"}, {"invoice.docx": BundleResourceReadStage.RUN}),
            ({"format": "xlsx", "template_file": "./invoice.xlsx"}, {"./invoice.xlsx": BundleResourceReadStage.RUN}),
            ({"template": "<p>{{ invoice.number }}</p>"}, {}),
            ({}, {}),
        ],
    )
    def test_the_file_it_reads_from_its_bundle_and_when(self, overrides: dict[str, Any], expected_reads: dict[str, BundleResourceReadStage]) -> None:
        """An HTML template file is read while the method loads, to check it against the inputs; an office one only when the step prints."""
        assert _blueprint(**overrides).bundle_resource_reads == expected_reads
