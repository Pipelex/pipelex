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
        validate_input_names(input_specs={"invoice": "Invoice", "supplier_name": "Text", "line_2": "Text?"})
        validate_input_names(input_specs={})

    def test_a_lone_dotted_name_names_both_remedies(self):
        """The root is not declared, so the message offers declaring it or binding the field, and no key is deletable."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs={"invoice.total": "Number"})

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["invoice.total"]
        assert error.redundant_input_name is None
        message = str(error)
        assert "Input 'invoice.total' is not a plain input name" in message
        assert "declare 'invoice' with its whole concept and read the field through it in the template (`$invoice.total`)" in message
        assert 'binding step (`{ from = "invoice.total", result = "total" }`)' in message

    def test_a_dotted_name_beside_its_root_is_redundant(self):
        """The root is declared in the same table, so the key is named as deletable, and the message still names the binding step."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs={"page": "Page", "page.page_view": "Image"})

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == ["page.page_view"]
        assert error.redundant_input_name == "page.page_view"
        assert error.dropped_input_marker is None
        message = str(error)
        assert "'page' is already declared, so delete this key" in message
        assert "Deleting 'page.page_view' drops" not in message
        assert 'binding step (`{ from = "page.page_view", result = "page_view" }`)' in message

    def test_the_redundant_name_is_reported_first(self):
        """The fixable name wins over an earlier lone one, so the fix loop can delete it before the author repairs the rest."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs={"supplier.name": "Text", "invoice": "Invoice", "invoice.total": "Number"})

        assert exc_info.value.redundant_input_name == "invoice.total"

    @pytest.mark.parametrize(
        ("input_specs", "reported_name", "dropped_input_marker"),
        [
            pytest.param({"data": "Text?", "data.text": "Text!"}, "data.text", "!", id="forced-key-after-an-optional-root"),
            pytest.param({"data.text": "Text!", "data": "Text?"}, "data.text", None, id="forced-key-before-an-optional-root"),
            pytest.param({"data": "Text!", "data.text": "Text!"}, "data.text", None, id="equal-markers"),
            pytest.param({"items": "Item", "items.x": "Text[]"}, "items.x", "[]", id="list-key-after-a-single-root"),
            pytest.param({"items.x": "Text[]", "items": "Item"}, "items.x", None, id="list-key-before-a-single-root"),
            pytest.param({"items": "Item[]", "items.x": "Text"}, "items.x", "", id="single-key-after-a-list-root"),
            pytest.param({"data": "Text?", "data.text": "Text"}, "data.text", "", id="plain-key-after-an-optional-root"),
            pytest.param({"page": "Page", "page.page_view": "Image"}, "page.page_view", None, id="differing-concept-only"),
            pytest.param({"data": "Text", "data.text": "Text[1]"}, "data.text", None, id="count-of-one-is-the-single-form"),
            pytest.param({"data": "Text?", "data.text": "Text!", "data.page": "Text?"}, "data.text", None, id="key-followed-under-its-root"),
            pytest.param(
                {"data": "Text?", "data.text": "Text!", "page": "Page", "page.page_view": "Image"},
                "page.page_view",
                None,
                id="safe-deletion-before-an-unsafe-one",
            ),
        ],
    )
    def test_a_redundant_name_carries_the_marker_its_deletion_would_drop(
        self,
        input_specs: dict[str, str],
        reported_name: str,
        dropped_input_marker: str | None,
    ):
        """The last declaration under a root set its presence and multiplicity, so deleting a key that set them differently is flagged."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs=input_specs)

        error = exc_info.value
        assert error.redundant_input_name == reported_name
        assert error.variable_names == [reported_name]
        assert error.dropped_input_marker == dropped_input_marker

    def test_the_refusal_warns_of_the_marker_its_deletion_would_drop(self):
        """The message carries the same warning as the fix: the marker the deletion drops, and to move it onto the root."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs={"data": "Text?", "data.text": "Text!"})

        message = str(exc_info.value)
        assert "'data' is already declared, so delete this key" in message
        assert "Deleting 'data.text' drops its marker `!`, which 'data' does not carry: move `!` onto 'data' if the root must carry it." in message
        assert 'binding step (`{ from = "data.text", result = "text" }`)' in message

    def test_the_refusal_warns_of_the_plain_form_its_deletion_would_drop(self):
        """A key with no marker under a root that carries one: the warning says to declare the root without its marker."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs={"data": "Text?", "data.text": "Text"})

        message = str(exc_info.value)
        assert "Deleting 'data.text' drops its plain single form" in message
        assert "declare 'data' without a marker if the root must be a plain single value." in message

    @pytest.mark.parametrize("malformed_name", ["InvoiceTotal", "2nd_total", "invoice-total", "Invoice.total", "invoice..total"])
    def test_a_malformed_name_is_refused_with_the_grammar(self, malformed_name: str):
        """A name that is not snake_case is refused with the grammar it breaks, even beside a declared root."""
        with pytest.raises(PipeValidationError) as exc_info:
            validate_input_names(input_specs={"invoice": "Invoice", malformed_name: "Number"})

        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert error.variable_names == [malformed_name]
        assert error.redundant_input_name is None
        assert f"Input '{malformed_name}' is not a valid input name" in str(error)
        assert "`[a-z][a-z0-9_]*`" in str(error)

    def test_a_plain_list_name_passes(self):
        check_input_list_name(input_list_name="pages")

    def test_a_dotted_list_name_is_refused(self):
        """A PipeBatch's list is one of its own inputs, so a dotted list name is refused, naming the binding step."""
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
