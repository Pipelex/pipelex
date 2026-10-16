from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.core.bundle_resources.bundle_resource import BundleResourceReadStage, canonical_resource_path_or_none
from pipelex.core.method_trees.file_references import BundleFileOrigin, BundleValidationContext
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint


def _blueprint(*, file_origin: BundleFileOrigin | None = None, **overrides: Any) -> PipeDocGenBlueprint:
    kwargs: dict[str, Any] = {"description": "Print the invoice", "inputs": {"invoice": "Invoice"}, "output": "Document", "format": "pdf"}
    kwargs.update(overrides)
    context = BundleValidationContext(file_origin=file_origin) if file_origin is not None else None
    return PipeDocGenBlueprint.model_validate(kwargs, context=context)


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
            ("posix_absolute_template_file", {"format": "docx", "template_file": "/srv/methods/invoice.docx"}, "it is absolute"),
            ("windows_rooted_template_file", {"format": "docx", "template_file": "\\methods\\invoice.docx"}, "it holds a backslash"),
            ("drive_absolute_template_file", {"format": "docx", "template_file": "C:/methods/invoice.docx"}, "it holds a colon"),
            ("drive_relative_template_file", {"format": "docx", "template_file": "C:invoice.docx"}, "it holds a colon"),
            ("unc_template_file", {"format": "docx", "template_file": "\\\\server\\share\\invoice.docx"}, "it holds a backslash"),
            ("posix_unc_template_file", {"format": "docx", "template_file": "//server/share/invoice.docx"}, "it is absolute"),
            ("colon_in_the_name", {"format": "docx", "template_file": "invoice:v2.docx"}, "it holds a colon"),
            ("url", {"format": "docx", "template_file": "https://example.com/invoice.docx"}, "it is a URL"),
            ("backslash_in_the_name", {"format": "docx", "template_file": "templates\\invoice.docx"}, "it holds a backslash"),
            ("empty_template_file", {"format": "docx", "template_file": " "}, "it is empty"),
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

    @pytest.mark.parametrize("template_file", ["invoice.docx", "./invoice.docx", "templates/invoice.docx", "templates//invoice.docx"])
    def test_a_path_inside_the_bundle_is_accepted_and_could_be_submitted(self, template_file: str) -> None:
        """A step's template file obeys the rule the files submitted with a bundle are keyed by, so it can always be submitted."""
        blueprint = _blueprint(format="docx", template_file=template_file)
        assert blueprint.template_file == template_file
        assert canonical_resource_path_or_none(path=template_file) is not None

    @pytest.mark.parametrize("file_origin", [None, BundleFileOrigin.METHOD_TREE], ids=["no_context", "method_tree"])
    @pytest.mark.parametrize("template_file", ["../invoice.docx", "templates/../invoice.docx", "../shared/templates/invoice.docx"])
    def test_a_path_climbing_through_dot_dot_is_left_to_the_method_tree(self, template_file: str, file_origin: BundleFileOrigin | None) -> None:
        """A `..` may climb to a file elsewhere in the method's tree, which only the load, holding the tree, can tell."""
        blueprint = _blueprint(file_origin=file_origin, format="docx", template_file=template_file)
        assert blueprint.template_file == template_file

    @pytest.mark.parametrize(
        ("template_file", "expected_reason"),
        [
            ("../invoice.docx", "it leaves the bundle through a '..' segment"),
            ("templates/../invoice.docx", "it leaves the bundle through a '..' segment"),
            ("templates/invoice\x00.docx", "it holds a NUL character"),
            ("/srv/methods/invoice.docx", "it is absolute"),
            ("C:invoice.docx", "it holds a colon"),
        ],
        ids=["leaves_the_bundle", "dot_dot_inside", "nul_character", "absolute", "colon"],
    )
    def test_a_bundle_reading_submitted_files_refuses_a_path_none_could_be_keyed_by(self, template_file: str, expected_reason: str) -> None:
        """A bundle loaded from a string reads only the files submitted with it, so its step is held to the rule they are keyed by."""
        with pytest.raises(ValidationError) as exc_info:
            _blueprint(file_origin=BundleFileOrigin.SUBMITTED_FILES, format="docx", template_file=template_file)

        (error,) = exc_info.value.errors()
        assert "PipeDocGen's 'template_file' names a file submitted with its bundle" in error["msg"]
        assert expected_reason in error["msg"]
        assert template_file not in error["msg"]

    @pytest.mark.parametrize("template_file", ["invoice.docx", "./invoice.docx", "templates/invoice.docx", "templates//invoice.docx"])
    def test_a_bundle_reading_submitted_files_accepts_a_path_inside_it(self, template_file: str) -> None:
        blueprint = _blueprint(file_origin=BundleFileOrigin.SUBMITTED_FILES, format="docx", template_file=template_file)
        assert blueprint.template_file == template_file

    @pytest.mark.parametrize("template_file", ["/srv/methods/invoice.docx", "C:/srv/methods/invoice.docx", "srv\\methods\\invoice.docx"])
    def test_the_refusal_of_a_template_file_outside_its_bundle_never_repeats_it(self, template_file: str) -> None:
        """A host library's step would otherwise put the host's own path in front of a caller."""
        with pytest.raises(ValidationError) as exc_info:
            _blueprint(format="docx", template_file=template_file)
        assert all("srv/methods" not in error["msg"] for error in exc_info.value.errors())

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
