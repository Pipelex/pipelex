# An input name is a plain name, on every pipe: anything else is refused as ``invalid_input_name``.
#
# These cases are pinned through the parser, the entry point a ``.mthds`` file goes through: a dotted input key
# on every operator, controller and signature is refused by the one shared check, a dotted key beside its
# declared root carries the enrichment the fix planner deletes it with, other malformed names are refused the
# same way, and so is a dotted PipeBatch ``input_list_name``. Each refused bundle is paired with the same bundle
# without the fault, which parses, so the refusal is shown to come from the name and nothing else.

import pytest

from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_machinery.pipe_blueprint import PipeType
from pipelex.validation_error_types import PipeValidationErrorType
from tests.unit.pipelex.pipe_machinery.test_data import InputNameRefusalTestData

_PIPE_TABLES = InputNameRefusalTestData.PIPE_TABLES
_SIGNATURE_ID = "PipeSignature"


def _bundle(*, pipe_table: str, added_input: str | None = None) -> str:
    """A bundle holding one pipe, `the_pipe`, with an input entry written first in its `inputs` when given."""
    if added_input is not None:
        pipe_table = pipe_table.replace("inputs = { ", f"inputs = {{ {added_input}, ", 1)
    return InputNameRefusalTestData.BUNDLE_HEADER + pipe_table


def _parse_errors(mthds_content: str) -> list[PipelexBundleBlueprintValidationErrorData]:
    with pytest.raises(MthdsParserError) as exc_info:
        MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="invoicing.mthds")
    return exc_info.value.validation_errors


def _the_one_error(mthds_content: str) -> PipelexBundleBlueprintValidationErrorData:
    errors = _parse_errors(mthds_content)
    assert len(errors) == 1, f"Expected exactly one error, got {[(error.error_type, error.message) for error in errors]}"
    return errors[0]


def _pipe_table(table_id: str) -> str:
    if table_id == _SIGNATURE_ID:
        return InputNameRefusalTestData.SIGNATURE_TABLE
    return _PIPE_TABLES[PipeType(table_id)]


_ALL_TABLE_IDS = [*(pipe_type.value for pipe_type in _PIPE_TABLES), _SIGNATURE_ID]


class TestInputNameRefusal:
    def test_every_pipe_kind_has_a_table(self) -> None:
        """Guard: the parametrized refusal below covers every executable pipe kind, so a new kind fails here until it is added."""
        assert set(_PIPE_TABLES) == set(PipeType)

    @pytest.mark.parametrize("table_id", _ALL_TABLE_IDS)
    def test_the_table_parses_without_the_dotted_key(self, table_id: str) -> None:
        """The control: each table is valid as written, so a refusal below comes from the added key alone."""
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_bundle(pipe_table=_pipe_table(table_id)), mthds_source="invoicing.mthds")
        assert blueprint.pipe is not None
        assert "the_pipe" in blueprint.pipe

    @pytest.mark.parametrize("table_id", _ALL_TABLE_IDS)
    def test_a_dotted_input_key_is_refused_on_every_pipe_kind(self, table_id: str) -> None:
        """A dotted key is refused by the one shared check, whichever operator, controller or signature declares it."""
        error = _the_one_error(_bundle(pipe_table=_pipe_table(table_id), added_input='"invoice.total" = "Number"'))

        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.pipe_code == "the_pipe"
        assert error.variable_names == ["invoice.total"]

    def test_a_lone_dotted_input_names_both_remedies_and_carries_no_fix_enrichment(self) -> None:
        """A lone dotted key, through the parser: the root is not declared, so nothing says its concept and the key is the author's to repair."""
        lone_table = _PIPE_TABLES[PipeType.PIPE_LLM].replace('inputs = { invoice = "Invoice" }', 'inputs = { "invoice.total" = "Number" }')
        lone_table = lone_table.replace("Summarize $invoice", "Summarize $invoice.total")

        error = _the_one_error(_bundle(pipe_table=lone_table))

        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["invoice.total"]
        assert error.redundant_input_name is None
        assert "declare 'invoice' with its whole concept" in error.message
        assert '{ from = "invoice.total", result = "total" }' in error.message

    def test_a_dotted_input_beside_its_root_carries_the_fix_enrichment(self) -> None:
        """The root is declared in the same table, so the key is redundant and the error says which key to delete."""
        error = _the_one_error(_bundle(pipe_table=_PIPE_TABLES[PipeType.PIPE_LLM], added_input='"invoice.total" = "Number"'))

        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.redundant_input_name == "invoice.total"
        assert "'invoice' is already declared, so delete this key" in error.message
        assert '{ from = "invoice.total", result = "total" }' in error.message

    def test_a_redundant_dotted_input_is_reported_before_a_lone_one(self) -> None:
        """The fixable name is reported first, so the fix loop deletes it and the lone one is left to the author."""
        error = _the_one_error(
            _bundle(pipe_table=_PIPE_TABLES[PipeType.PIPE_LLM], added_input='"supplier.name" = "Text", "invoice.total" = "Number"')
        )

        assert error.redundant_input_name == "invoice.total"
        assert error.variable_names == ["invoice.total"]

    @pytest.mark.parametrize("malformed_name", ["InvoiceTotal", "2nd_total", "invoice-total", "_total", "invoice..total", "Invoice.total"])
    def test_a_malformed_input_name_is_refused(self, malformed_name: str) -> None:
        """Any name that is not a plain snake_case identifier is refused the same way, and is never deletable."""
        error = _the_one_error(_bundle(pipe_table=_PIPE_TABLES[PipeType.PIPE_LLM], added_input=f'"{malformed_name}" = "Number"'))

        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == [malformed_name]
        assert error.redundant_input_name is None
        assert "[a-z][a-z0-9_]*" in error.message

    def test_a_dotted_batch_list_name_is_refused(self) -> None:
        """`input_list_name` is a plain input name, so a path into a field of a declared input is refused."""
        batch_table = InputNameRefusalTestData.BATCH_OVER_A_FIELD_TABLE
        error = _the_one_error(_bundle(pipe_table=batch_table))

        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["catalog.pages"]
        assert error.redundant_input_name is None
        assert '{ from = "catalog.pages", result = "pages" }' in error.message
        assert '`{ pipe = "total_page", batch_over = "catalog.pages", batch_as = "page" }`' in error.message

    def test_a_dotted_batch_list_declared_as_an_input_is_refused(self) -> None:
        """The other spelling of a dotted batch list: the list declared under its dotted name is refused by the shared input-name check."""
        batch_table = _PIPE_TABLES[PipeType.PIPE_BATCH].replace('inputs = { invoices = "Invoice[]" }', 'inputs = { "ledger.invoices" = "Invoice[]" }')
        batch_table = batch_table.replace('input_list_name = "invoices"', 'input_list_name = "ledger.invoices"')

        error = _the_one_error(_bundle(pipe_table=batch_table))

        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["ledger.invoices"]
