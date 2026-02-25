"""Unit tests for ConstructFieldBlueprint - defines how a single field is composed.

Tests cover the 4 composition methods:
1. Fixed value: `field = "literal"` or `field = 42`
2. Variable reference: `field = { from = "path.to.var" }`
3. Template: `field = { template = "text with $var" }`
4. Nested construct: dict with nested fields (recursive)
"""

from typing import Any, ClassVar

import pytest

from pipelex.pipe_operators.compose.construct_blueprint import (
    ConstructFieldBlueprint,
    ConstructFieldMethod,
)
from pipelex.pipe_operators.compose.exceptions import (
    ConstructFieldBlueprintTypeError,
    ConstructFieldBlueprintValueError,
)


class ConstructFieldBlueprintTestData:
    """Test data for ConstructFieldBlueprint tests."""

    # Fixed value cases: (test_id, raw_input, expected_method, expected_value)
    FIXED_STRING: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "fixed_string",
        "Monthly Report",
        ConstructFieldMethod.FIXED,
        "Monthly Report",
    )

    FIXED_INT: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "fixed_int",
        42,
        ConstructFieldMethod.FIXED,
        42,
    )

    FIXED_FLOAT: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "fixed_float",
        3.14,
        ConstructFieldMethod.FIXED,
        3.14,
    )

    FIXED_BOOL: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "fixed_bool",
        True,
        ConstructFieldMethod.FIXED,
        True,
    )

    # Variable reference cases: (test_id, raw_input, expected_method, expected_path)
    VAR_REF_SIMPLE: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "var_ref_simple",
        {"from": "deal.customer_name"},
        ConstructFieldMethod.FROM_VAR,
        "deal.customer_name",
    )

    VAR_REF_NESTED_PATH: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "var_ref_nested_path",
        {"from": "order.billing_address.city"},
        ConstructFieldMethod.FROM_VAR,
        "order.billing_address.city",
    )

    # Template cases: (test_id, raw_input, expected_method, expected_template)
    TEMPLATE_SIMPLE: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "template_simple",
        {"template": "Hello $name"},
        ConstructFieldMethod.TEMPLATE,
        "Hello $name",
    )

    TEMPLATE_MULTI_VAR: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "template_multi_var",
        {"template": "Deal worth $deal.amount with $deal.customer_name"},
        ConstructFieldMethod.TEMPLATE,
        "Deal worth $deal.amount with $deal.customer_name",
    )

    TEMPLATE_WITH_JINJA2: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "template_with_jinja2",
        {"template": "INV-{{ order.id | upper }}"},
        ConstructFieldMethod.TEMPLATE,
        "INV-{{ order.id | upper }}",
    )

    # Nested construct cases: (test_id, raw_input, expected_method)
    NESTED_SIMPLE: ClassVar[tuple[str, Any, ConstructFieldMethod]] = (
        "nested_simple",
        {
            "street": "123 Main St",
            "city": {"from": "customer.city"},
        },
        ConstructFieldMethod.NESTED,
    )

    NESTED_DEEP: ClassVar[tuple[str, Any, ConstructFieldMethod]] = (
        "nested_deep",
        {
            "line1": {"from": "addr.line1"},
            "location": {
                "city": {"from": "addr.city"},
                "country": "France",
            },
        },
        ConstructFieldMethod.NESTED,
    )

    # All fixed value cases
    FIXED_VALUE_CASES: ClassVar[list[tuple[str, Any, ConstructFieldMethod, Any]]] = [
        FIXED_STRING,
        FIXED_INT,
        FIXED_FLOAT,
        FIXED_BOOL,
    ]

    # All variable reference cases
    VAR_REF_CASES: ClassVar[list[tuple[str, Any, ConstructFieldMethod, Any]]] = [
        VAR_REF_SIMPLE,
        VAR_REF_NESTED_PATH,
    ]

    # All template cases
    TEMPLATE_CASES: ClassVar[list[tuple[str, Any, ConstructFieldMethod, Any]]] = [
        TEMPLATE_SIMPLE,
        TEMPLATE_MULTI_VAR,
        TEMPLATE_WITH_JINJA2,
    ]

    # All nested construct cases
    NESTED_CASES: ClassVar[list[tuple[str, Any, ConstructFieldMethod]]] = [
        NESTED_SIMPLE,
        NESTED_DEEP,
    ]

    # Fixed list value case
    FIXED_LIST: ClassVar[tuple[str, Any, ConstructFieldMethod, Any]] = (
        "fixed_list",
        ["item1", "item2", "item3"],
        ConstructFieldMethod.FIXED,
        ["item1", "item2", "item3"],
    )

    # Variable reference with list_to_dict_keyed_by modifier
    VAR_REF_LIST_TO_DICT: ClassVar[tuple[str, dict[str, Any], ConstructFieldMethod, str, str]] = (
        "var_ref_list_to_dict",
        {"from": "items", "list_to_dict_keyed_by": "id"},
        ConstructFieldMethod.FROM_VAR,
        "items",
        "id",
    )


class TestConstructFieldBlueprint:
    """Tests for ConstructFieldBlueprint parsing and method detection."""

    @pytest.mark.parametrize(
        ("test_id", "raw_input", "expected_method", "expected_value"),
        ConstructFieldBlueprintTestData.FIXED_VALUE_CASES,
    )
    def test_fixed_value_detection(
        self,
        test_id: str,
        raw_input: Any,
        expected_method: ConstructFieldMethod,
        expected_value: Any,
    ):
        """Test that fixed values (literals) are correctly detected and stored."""
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == expected_method, f"Failed for {test_id}"
        assert blueprint.fixed_value == expected_value, f"Failed for {test_id}"
        assert blueprint.from_path is None, f"from_path should be None for {test_id}"
        assert blueprint.template is None, f"template should be None for {test_id}"
        assert blueprint.nested is None, f"nested should be None for {test_id}"

    @pytest.mark.parametrize(
        ("test_id", "raw_input", "expected_method", "expected_path"),
        ConstructFieldBlueprintTestData.VAR_REF_CASES,
    )
    def test_var_ref_detection(
        self,
        test_id: str,
        raw_input: Any,
        expected_method: ConstructFieldMethod,
        expected_path: str,
    ):
        """Test that variable references (from) are correctly detected and stored."""
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == expected_method, f"Failed for {test_id}"
        assert blueprint.from_path == expected_path, f"Failed for {test_id}"
        assert blueprint.fixed_value is None, f"fixed_value should be None for {test_id}"
        assert blueprint.template is None, f"template should be None for {test_id}"
        assert blueprint.nested is None, f"nested should be None for {test_id}"

    @pytest.mark.parametrize(
        ("test_id", "raw_input", "expected_method", "expected_template"),
        ConstructFieldBlueprintTestData.TEMPLATE_CASES,
    )
    def test_template_detection(
        self,
        test_id: str,
        raw_input: Any,
        expected_method: ConstructFieldMethod,
        expected_template: str,
    ):
        """Test that templates are correctly detected and stored."""
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == expected_method, f"Failed for {test_id}"
        assert blueprint.template == expected_template, f"Failed for {test_id}"
        assert blueprint.fixed_value is None, f"fixed_value should be None for {test_id}"
        assert blueprint.from_path is None, f"from_path should be None for {test_id}"
        assert blueprint.nested is None, f"nested should be None for {test_id}"

    @pytest.mark.parametrize(
        ("test_id", "raw_input", "expected_method"),
        ConstructFieldBlueprintTestData.NESTED_CASES,
    )
    def test_nested_detection(
        self,
        test_id: str,
        raw_input: dict[str, Any],
        expected_method: ConstructFieldMethod,
    ):
        """Test that nested constructs are correctly detected."""
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == expected_method, f"Failed for {test_id}"
        assert blueprint.nested is not None, f"nested should not be None for {test_id}"
        assert blueprint.fixed_value is None, f"fixed_value should be None for {test_id}"
        assert blueprint.from_path is None, f"from_path should be None for {test_id}"
        assert blueprint.template is None, f"template should be None for {test_id}"

    def test_nested_has_correct_child_blueprints(self):
        """Test that nested constructs have correctly parsed child field blueprints."""
        raw_input = {
            "street": "123 Main St",
            "city": {"from": "customer.city"},
            "country": {"template": "Country: $loc.country"},
        }
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == ConstructFieldMethod.NESTED
        assert blueprint.nested is not None
        assert len(blueprint.nested.fields) == 3

        # Check street is fixed
        assert blueprint.nested.fields["street"].method == ConstructFieldMethod.FIXED
        assert blueprint.nested.fields["street"].fixed_value == "123 Main St"

        # Check city is from_var
        assert blueprint.nested.fields["city"].method == ConstructFieldMethod.FROM_VAR
        assert blueprint.nested.fields["city"].from_path == "customer.city"

        # Check country is template
        assert blueprint.nested.fields["country"].method == ConstructFieldMethod.TEMPLATE
        assert blueprint.nested.fields["country"].template == "Country: $loc.country"

    def test_fixed_list_value_detection(self):
        """Test that list values are correctly detected as FIXED method."""
        test_id, raw_input, expected_method, expected_value = ConstructFieldBlueprintTestData.FIXED_LIST
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == expected_method, f"Failed for {test_id}"
        assert blueprint.fixed_value == expected_value, f"Failed for {test_id}"
        assert blueprint.from_path is None
        assert blueprint.template is None
        assert blueprint.nested is None

    def test_from_with_list_to_dict_keyed_by(self):
        """Test variable reference with list_to_dict_keyed_by modifier."""
        test_id, raw_input, expected_method, expected_path, expected_key_attr = ConstructFieldBlueprintTestData.VAR_REF_LIST_TO_DICT
        blueprint = ConstructFieldBlueprint.make_from_raw(raw_input)

        assert blueprint.method == expected_method, f"Failed for {test_id}"
        assert blueprint.from_path == expected_path, f"Failed for {test_id}"
        assert blueprint.list_to_dict_keyed_by == expected_key_attr, f"Failed for {test_id}"


class TestConstructFieldBlueprintValidation:
    """Tests for ConstructFieldBlueprint validation."""

    def test_empty_dict_raises_error(self):
        """Empty dict should raise an error - ambiguous construct."""
        with pytest.raises(ValueError, match="empty"):
            ConstructFieldBlueprint.make_from_raw({})

    def test_dict_with_both_from_and_template_raises_error(self):
        """Dict with both 'from' and 'template' keys should raise an error."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            ConstructFieldBlueprint.make_from_raw(
                {
                    "from": "deal.name",
                    "template": "Hello $name",
                }
            )

    def test_none_value_raises_error(self):
        """None value should raise an error."""
        with pytest.raises(ConstructFieldBlueprintValueError, match="None"):
            ConstructFieldBlueprint.make_from_raw(None)

    def test_from_with_extra_keys_raises_error(self):
        """Dict with 'from' and unexpected keys should raise error."""
        with pytest.raises(ConstructFieldBlueprintValueError, match="unexpected keys"):
            ConstructFieldBlueprint.make_from_raw(
                {
                    "from": "deal.name",
                    "invalid_key": "value",
                }
            )

    def test_from_value_not_string_raises_type_error(self):
        """'from' value must be a string path."""
        with pytest.raises(ConstructFieldBlueprintTypeError, match="string path"):
            ConstructFieldBlueprint.make_from_raw({"from": 123})

    def test_list_to_dict_keyed_by_not_string_raises_type_error(self):
        """'list_to_dict_keyed_by' value must be a string."""
        with pytest.raises(ConstructFieldBlueprintTypeError, match="string attribute name"):
            ConstructFieldBlueprint.make_from_raw(
                {
                    "from": "items",
                    "list_to_dict_keyed_by": 123,
                }
            )

    def test_template_with_extra_keys_raises_error(self):
        """Dict with 'template' and extra keys should raise error."""
        with pytest.raises(ConstructFieldBlueprintValueError, match="only have the 'template' key"):
            ConstructFieldBlueprint.make_from_raw(
                {
                    "template": "Hello $name",
                    "extra": "not allowed",
                }
            )

    def test_template_value_not_string_raises_type_error(self):
        """'template' value must be a string."""
        with pytest.raises(ConstructFieldBlueprintTypeError, match="string"):
            ConstructFieldBlueprint.make_from_raw({"template": 123})

    def test_unsupported_type_raises_type_error(self):
        """Unsupported types should raise TypeError."""
        with pytest.raises(ConstructFieldBlueprintTypeError, match="Unsupported"):
            ConstructFieldBlueprint.make_from_raw(object())
