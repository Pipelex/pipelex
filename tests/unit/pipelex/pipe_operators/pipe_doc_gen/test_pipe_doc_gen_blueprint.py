import re
from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.cogt.doc_gen.table_fill import CellPolicy, TableFill
from pipelex.core.bundle_resources.bundle_resource import canonical_resource_path_or_none
from pipelex.core.method_trees.file_references import BundleFileOrigin, BundleValidationContext
from pipelex.pipe_operators.doc_gen.pipe_doc_gen_blueprint import PipeDocGenBlueprint


def _blueprint(*, file_origin: BundleFileOrigin | None = None, **overrides: Any) -> PipeDocGenBlueprint:
    kwargs: dict[str, Any] = {"description": "Print the invoice", "inputs": {"invoice": "Invoice"}, "output": "Document", "format": "pdf"}
    kwargs.update(overrides)
    context = BundleValidationContext(file_origin=file_origin) if file_origin is not None else None
    return PipeDocGenBlueprint.model_validate(kwargs, context=context)


_NO_FILE: set[str] = set()
_NO_OVERRIDE: dict[str, Any] = {}
_WORKBOOK_INPUTS: dict[str, str] = {"workbook": "Document", "rows": "Row[]", "maybe": "Document?", "workbooks": "Document[]"}


class TestPipeDocGenBlueprint:
    def test_output_filename_alone_names_the_document(self) -> None:
        """The standard's key is accepted alone: the produced file takes its name when the step ends."""
        blueprint = _blueprint(output_filename="Invoice {{ invoice.number }}")
        assert blueprint.output_filename == "Invoice {{ invoice.number }}"
        assert blueprint.filename is None

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
            (
                "filename_beside_output_filename",
                {"filename": "invoice-{{ invoice.number }}", "output_filename": "Invoice {{ invoice.number }}"},
                "both 'filename' and 'output_filename'",
            ),
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
        ("overrides", "expected_files"),
        [
            ({"template_file": "templates/invoice.html"}, {"templates/invoice.html"}),
            ({"format": "docx", "template_file": "invoice.docx"}, {"invoice.docx"}),
            ({"format": "xlsx", "template_file": "./invoice.xlsx"}, {"./invoice.xlsx"}),
            ({"template": "<p>{{ invoice.number }}</p>"}, _NO_FILE),
            (_NO_OVERRIDE, _NO_FILE),
        ],
    )
    def test_the_file_of_its_tree_it_names(self, overrides: dict[str, Any], expected_files: set[str]) -> None:
        """A step names its template file, as written; the print stage reads it, an HTML one checked at load too."""
        assert _blueprint(**overrides).named_file_references == expected_files

    @pytest.mark.parametrize(
        ("overrides", "expected_template_input", "expected_table_fill"),
        [
            ({"format": "xlsx", "template_input": "workbook", "table_fill": "append"}, "workbook", TableFill.APPEND),
            ({"format": "xlsx", "template_input": "workbook"}, "workbook", None),
            ({"format": "docx", "template_input": "workbook", "table_fill": "replace"}, "workbook", TableFill.REPLACE),
            ({"format": "pptx", "template_input": "workbook"}, "workbook", None),
            ({"format": "xlsx", "template_file": "expenses.xlsx", "table_fill": "append"}, None, TableFill.APPEND),
        ],
        ids=["xlsx_append", "xlsx_default_fill", "docx_replace", "pptx_needs_no_template_file", "template_file_append"],
    )
    def test_accepted_template_inputs_and_fills(
        self, overrides: dict[str, Any], expected_template_input: str | None, expected_table_fill: TableFill | None
    ) -> None:
        blueprint = _blueprint(inputs=_WORKBOOK_INPUTS, **overrides)
        assert blueprint.template_input == expected_template_input
        assert blueprint.table_fill == expected_table_fill
        assert blueprint.named_file_references == ({blueprint.template_file} if blueprint.template_file else _NO_FILE)

    @pytest.mark.parametrize(
        ("overrides", "expected_message"),
        [
            ({"format": "xlsx", "template_input": "workbook", "template_file": "expenses.xlsx"}, "cannot be used with 'template' or 'template_file'"),
            ({"format": "pdf", "template_input": "workbook", "template": "<p>x</p>"}, "cannot be used with 'template' or 'template_file'"),
            ({"format": "pdf", "template_input": "workbook"}, "'template_input' is for an office format"),
            ({"format": "xlsx", "template_input": "ledger"}, "names 'ledger', which is not one of the step's inputs"),
            ({"format": "xlsx", "template_input": "workbooks"}, "a list ('Document[]')"),
            ({"format": "xlsx", "template_input": "maybe"}, "an optional input ('Document?')"),
            ({"format": "docx", "template_input": "workbook", "table_fill": "append"}, "is for the 'xlsx' format only"),
            ({"format": "pptx", "template_input": "workbook", "table_fill": "append"}, "is for the 'xlsx' format only"),
            ({"format": "xlsx", "table_fill": "append"}, "fills the Tables of a template file, and this step has none"),
            ({"format": "pdf", "table_fill": "replace"}, "fills the Tables of a template file, and this step has none"),
            ({"format": "xlsx", "template_input": "workbook", "table_fill": "upsert"}, "table_fill"),
        ],
        ids=[
            "with_template_file",
            "with_inline_template",
            "pdf",
            "undeclared_input",
            "list_input",
            "optional_input",
            "append_on_docx",
            "append_on_pptx",
            "fill_without_template",
            "fill_on_the_pdf_auto_layout",
            "unknown_fill",
        ],
    )
    def test_refused_template_inputs_and_fills(self, overrides: dict[str, Any], expected_message: str) -> None:
        with pytest.raises(ValidationError, match=re.escape(expected_message)):
            _blueprint(inputs=_WORKBOOK_INPUTS, **overrides)

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({"match_on": ["invoice_number"]}, (["invoice_number"], None, None)),
            ({"match_on": ["sheet", "line"], "cells": "overwrite"}, (["sheet", "line"], None, CellPolicy.OVERWRITE)),
            ({"match_row": "row"}, (None, "row", None)),
            ({"match_row": "row", "cells": "fill_empty"}, (None, "row", CellPolicy.FILL_EMPTY)),
        ],
        ids=["by_key", "by_composite_key_overwriting", "by_row", "by_row_filling_empty_cells"],
    )
    def test_accepted_updates(self, overrides: dict[str, Any], expected: tuple[list[str] | None, str | None, CellPolicy | None]) -> None:
        blueprint = _blueprint(inputs=_WORKBOOK_INPUTS, format="xlsx", template_input="workbook", table_fill="update", **overrides)
        assert blueprint.table_fill == TableFill.UPDATE
        assert (blueprint.match_on, blueprint.match_row, blueprint.cells) == expected

    @pytest.mark.parametrize(
        ("overrides", "expected_message"),
        [
            ({"table_fill": "update"}, "name the fields whose columns are the Table's key with 'match_on'"),
            ({"table_fill": "update", "match_on": ["id"], "match_row": "row"}, "by 'match_on' or by 'match_row', not both"),
            ({"table_fill": "update", "match_on": []}, "names the fields whose columns are the Table's key, and it names none"),
            ({"table_fill": "update", "match_on": ["id", "id"]}, "names each key field once, and it repeats 'id'"),
            ({"table_fill": "update", "match_row": "row", "cells": "erase"}, "cells"),
            ({"table_fill": "append", "match_on": ["id"]}, "'match_on' says how 'table_fill = \"update\"'"),
            ({"match_row": "row"}, "this step uses the default 'table_fill = \"replace\"': remove 'match_row'"),
            ({"table_fill": "replace", "cells": "overwrite"}, "'cells' says how 'table_fill = \"update\"'"),
            ({"format": "docx", "table_fill": "update", "match_on": ["id"]}, "is for the 'xlsx' format only"),
        ],
        ids=[
            "no_way_to_match",
            "both_ways_to_match",
            "empty_key",
            "repeated_key",
            "unknown_cell_policy",
            "key_on_append",
            "row_on_the_default_fill",
            "cells_on_replace",
            "update_on_docx",
        ],
    )
    def test_refused_updates(self, overrides: dict[str, Any], expected_message: str) -> None:
        kwargs: dict[str, Any] = {"format": "xlsx", "template_input": "workbook"}
        kwargs.update(overrides)
        with pytest.raises(ValidationError, match=re.escape(expected_message)):
            _blueprint(inputs=_WORKBOOK_INPUTS, **kwargs)


class TestPipeDocGenSheetRangeBlueprint:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"table_fill": "append", "sheet_range": {"list": "rows"}},
            {"table_fill": "update", "match_on": ["id"], "sheet_range": {"list": "rows", "sheet": "Expenses", "header_row": 3}},
            {"table_fill": "update", "match_row": "row", "sheet_range": {"list": "rows"}},
        ],
        ids=["append", "update-by-key", "update-by-row"],
    )
    def test_accepted_sheet_ranges(self, overrides: dict[str, Any]) -> None:
        blueprint = _blueprint(inputs=_WORKBOOK_INPUTS, format="xlsx", template_input="workbook", **overrides)

        assert blueprint.sheet_range is not None
        assert blueprint.sheet_range.list == "rows"

    def test_a_template_file_takes_a_sheet_range(self) -> None:
        blueprint = _blueprint(
            inputs=_WORKBOOK_INPUTS, format="xlsx", template_file="expenses.xlsx", table_fill="append", sheet_range={"list": "rows"}
        )

        assert blueprint.sheet_range is not None

    @pytest.mark.parametrize(
        ("overrides", "expected_message"),
        [
            ({"template_input": "workbook", "sheet_range": {"list": "rows"}}, "this step uses the default 'table_fill = \"replace\"'"),
            (
                {"template_input": "workbook", "table_fill": "replace", "sheet_range": {"list": "rows"}},
                "this step uses 'table_fill = \"replace\"': a replace shrinks the rows to the list's length",
            ),
            ({"table_fill": "append", "sheet_range": {"list": "rows"}}, "fills the Tables of a template file, and this step has none"),
            (
                {"format": "docx", "template_input": "workbook", "table_fill": "append", "sheet_range": {"list": "rows"}},
                "is for the 'xlsx' format only",
            ),
            ({"template_input": "workbook", "table_fill": "append", "sheet_range": {}}, "list"),
            ({"template_input": "workbook", "table_fill": "append", "sheet_range": {"list": ""}}, "fills the range in 'list', and it names none"),
            ({"template_input": "workbook", "table_fill": "append", "sheet_range": {"list": "rows", "header_row": 0}}, "greater than or equal to 1"),
            ({"template_input": "workbook", "table_fill": "append", "sheet_range": {"list": "rows", "table": "T"}}, "Extra inputs are not permitted"),
        ],
        ids=["default-replace", "replace", "no-template", "docx", "no-list", "empty-list", "row-zero", "unknown-field"],
    )
    def test_refused_sheet_ranges(self, overrides: dict[str, Any], expected_message: str) -> None:
        kwargs: dict[str, Any] = {"format": "xlsx"}
        kwargs.update(overrides)
        with pytest.raises(ValidationError, match=re.escape(expected_message)):
            _blueprint(inputs=_WORKBOOK_INPUTS, **kwargs)
