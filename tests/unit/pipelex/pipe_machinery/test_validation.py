import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_machinery.validation import check_input_list_name, is_valid_input_name, validate_input_names
from pipelex.validation_error_types import PipeValidationErrorType


class TestInputNameValidation:
    @pytest.mark.parametrize(
        ("input_name", "expected_result"),
        [
            # A plain snake_case identifier
            ("my_input", True),
            ("input_123", True),
            ("my_input_field", True),
            ("a", True),
            ("a_b", True),
            ("trailing_", True),
            # Dotted: an input names one whole value, never a field of one
            ("my_input.field_name", False),
            ("my_input.field_name.nested_field", False),
            ("a.b", False),
            # Not snake_case
            ("myInput", False),
            ("MyInput", False),
            ("my-input", False),
            ("my input", False),
            ("123_input", False),
            ("2nd_total", False),
            ("_private", False),
            ("", False),
            (".", False),
            (".my_input", False),
            ("my_input.", False),
            ("my_input..field", False),
            ("my_input\n", False),
        ],
    )
    def test_is_valid_input_name(self, input_name: str, expected_result: bool):
        assert is_valid_input_name(input_name) == expected_result

    def test_plain_names_pass(self):
        validate_input_names(input_names=["invoice", "supplier_name", "line_2"])
        validate_input_names(input_names=[])

    def test_a_lone_dotted_name_names_both_remedies(self):
        """I1: the root is not declared, so the message offers declaring it or binding the field, and no key is deletable."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_names=["invoice.total"])

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["invoice.total"]
        assert error.redundant_input_name is None
        message = str(error)
        assert "Input 'invoice.total' is not a plain input name" in message
        assert "declare 'invoice' with its whole concept and read the field through it in the template (`$invoice.total`)" in message
        assert 'binding step (`{ from = "invoice.total", result = "total" }`)' in message

    def test_a_dotted_name_beside_its_root_is_redundant(self):
        """I2: the root is declared in the same table, so the key is named as deletable, and the message still names the binding step."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_names=["page", "page.page_view"])

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["page.page_view"]
        assert error.redundant_input_name == "page.page_view"
        message = str(error)
        assert "'page' is already declared, so delete this key" in message
        assert 'binding step (`{ from = "page.page_view", result = "page_view" }`)' in message

    def test_the_redundant_name_is_reported_first(self):
        """The fixable name wins over an earlier lone one, so the fix loop can delete it before the author repairs the rest."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_names=["supplier.name", "invoice", "invoice.total"])

        assert exc_info.value.redundant_input_name == "invoice.total"

    @pytest.mark.parametrize("malformed_name", ["InvoiceTotal", "2nd_total", "invoice-total", "Invoice.total", "invoice..total"])
    def test_a_malformed_name_is_refused_with_the_grammar(self, malformed_name: str):
        """I4: a name that is not snake_case is refused with the grammar it breaks, even beside a declared root."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_names=["invoice", malformed_name])

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == [malformed_name]
        assert error.redundant_input_name is None
        assert f"Input '{malformed_name}' is not a valid input name" in str(error)
        assert "`[a-z][a-z0-9_]*`" in str(error)

    def test_a_plain_list_name_passes(self):
        check_input_list_name(input_list_name="pages")

    def test_a_dotted_list_name_is_refused(self):
        """I5: a PipeBatch's list is one of its own inputs, so a dotted list name is refused, naming the binding step."""
        with pytest.raises(PipeValidationError) as exc_info:
            check_input_list_name(input_list_name="catalog.pages")

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["catalog.pages"]
        message = str(error)
        assert "`input_list_name` 'catalog.pages' is not a plain input name" in message
        assert '`input_list_name = "pages"`' in message
        assert '{ from = "catalog.pages", result = "pages" }' in message

    def test_a_malformed_list_name_is_refused(self):
        with pytest.raises(PipeValidationError) as exc_info:
            check_input_list_name(input_list_name="CatalogPages")

        assert exc_info.value.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert "is not a valid input name" in str(exc_info.value)
