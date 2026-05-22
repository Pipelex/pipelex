"""Unit tests for ConstructBlueprint - the container for field blueprints.

ConstructBlueprint is parsed from the `[pipe.name.construct]` section in MTHDS files.
"""

from typing import Any, ClassVar

import pytest

from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint, ConstructFieldMethod


class ConstructBlueprintTestData:
    """Test data for ConstructBlueprint tests."""

    # Simple flat construct (all fixed values)
    FLAT_FIXED_ONLY: ClassVar[tuple[str, dict[str, Any]]] = (
        "flat_fixed_only",
        {
            "title": "Monthly Report",
            "version": 1,
            "is_draft": False,
        },
    )

    # Flat construct with mixed methods
    FLAT_MIXED: ClassVar[tuple[str, dict[str, Any]]] = (
        "flat_mixed",
        {
            "report_title": "Monthly Sales Report",
            "customer_name": {"from": "deal.customer_name"},
            "deal_value": {"from": "deal.amount"},
            "summary_text": {"template": "Deal worth $deal.amount with $deal.customer_name"},
        },
    )

    # Construct with nested structure
    WITH_NESTED: ClassVar[tuple[str, dict[str, Any]]] = (
        "with_nested",
        {
            "invoice_number": {"template": "INV-$order.id"},
            "total": {"from": "order.total_amount"},
            "billing_address": {
                "street": {"from": "customer.address.street"},
                "city": {"from": "customer.address.city"},
                "country": "France",
            },
        },
    )

    # Deeply nested construct
    DEEPLY_NESTED: ClassVar[tuple[str, dict[str, Any]]] = (
        "deeply_nested",
        {
            "name": {"from": "company.name"},
            "headquarters": {
                "address": {
                    "street": {"from": "hq.street"},
                    "city": {"from": "hq.city"},
                },
                "phone": {"template": "+$hq.country_code $hq.phone"},
            },
        },
    )

    ALL_CASES: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        FLAT_FIXED_ONLY,
        FLAT_MIXED,
        WITH_NESTED,
        DEEPLY_NESTED,
    ]


class TestConstructBlueprintParsing:
    """Tests for ConstructBlueprint parsing from raw dict."""

    @pytest.mark.parametrize(
        ("test_id", "raw_construct"),
        ConstructBlueprintTestData.ALL_CASES,
    )
    def test_make_from_raw_succeeds(
        self,
        test_id: str,
        raw_construct: dict[str, Any],
    ):
        """Test that valid raw construct dicts are successfully parsed."""
        blueprint = ConstructBlueprint.make_from_raw(raw_construct)

        assert blueprint is not None, f"Failed for {test_id}"
        assert len(blueprint.fields) == len(raw_construct), f"Field count mismatch for {test_id}"

    def test_flat_fixed_only_has_correct_fields(self):
        """Test flat construct with only fixed values has correct field blueprints."""
        raw = ConstructBlueprintTestData.FLAT_FIXED_ONLY[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        assert blueprint.fields["title"].method == ConstructFieldMethod.FIXED
        assert blueprint.fields["title"].fixed_value == "Monthly Report"

        assert blueprint.fields["version"].method == ConstructFieldMethod.FIXED
        assert blueprint.fields["version"].fixed_value == 1

        assert blueprint.fields["is_draft"].method == ConstructFieldMethod.FIXED
        assert blueprint.fields["is_draft"].fixed_value is False

    def test_flat_mixed_has_correct_field_methods(self):
        """Test flat construct with mixed methods has correct field types."""
        raw = ConstructBlueprintTestData.FLAT_MIXED[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        assert blueprint.fields["report_title"].method == ConstructFieldMethod.FIXED
        assert blueprint.fields["customer_name"].method == ConstructFieldMethod.FROM_VAR
        assert blueprint.fields["deal_value"].method == ConstructFieldMethod.FROM_VAR
        assert blueprint.fields["summary_text"].method == ConstructFieldMethod.TEMPLATE

    def test_with_nested_has_nested_blueprint(self):
        """Test construct with nested structure has nested blueprint."""
        raw = ConstructBlueprintTestData.WITH_NESTED[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        assert blueprint.fields["invoice_number"].method == ConstructFieldMethod.TEMPLATE
        assert blueprint.fields["total"].method == ConstructFieldMethod.FROM_VAR
        assert blueprint.fields["billing_address"].method == ConstructFieldMethod.NESTED

        # Check nested blueprint
        nested = blueprint.fields["billing_address"].nested
        assert nested is not None
        assert len(nested.fields) == 3
        assert nested.fields["street"].method == ConstructFieldMethod.FROM_VAR
        assert nested.fields["city"].method == ConstructFieldMethod.FROM_VAR
        assert nested.fields["country"].method == ConstructFieldMethod.FIXED
        assert nested.fields["country"].fixed_value == "France"

    def test_deeply_nested_parses_correctly(self):
        """Test deeply nested construct parses all levels."""
        raw = ConstructBlueprintTestData.DEEPLY_NESTED[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        # Level 1
        assert blueprint.fields["name"].method == ConstructFieldMethod.FROM_VAR
        assert blueprint.fields["headquarters"].method == ConstructFieldMethod.NESTED

        # Level 2 (headquarters)
        hq = blueprint.fields["headquarters"].nested
        assert hq is not None
        assert hq.fields["address"].method == ConstructFieldMethod.NESTED
        assert hq.fields["phone"].method == ConstructFieldMethod.TEMPLATE

        # Level 3 (address)
        address = hq.fields["address"].nested
        assert address is not None
        assert address.fields["street"].method == ConstructFieldMethod.FROM_VAR
        assert address.fields["street"].from_path == "hq.street"
        assert address.fields["city"].method == ConstructFieldMethod.FROM_VAR


class TestConstructBlueprintFieldAccess:
    """Tests for field access utilities in ConstructBlueprint."""

    def test_get_required_variables_flat(self):
        """Test extraction of required variables from flat construct returns root names only."""
        raw = ConstructBlueprintTestData.FLAT_MIXED[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        required_vars = blueprint.get_required_variables()

        # Should return root names only (e.g., 'deal' from 'deal.customer_name')
        assert "deal" in required_vars
        # Should NOT contain full dotted paths
        assert "deal.customer_name" not in required_vars
        assert "deal.amount" not in required_vars

    def test_get_required_variables_nested(self):
        """Test extraction of required variables includes nested constructs with root names only."""
        raw = ConstructBlueprintTestData.WITH_NESTED[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        required_vars = blueprint.get_required_variables()

        # Should return root names only from all levels (including nested constructs)
        assert "order" in required_vars
        assert "customer" in required_vars
        # Should NOT contain full dotted paths
        assert "order.id" not in required_vars
        assert "order.total_amount" not in required_vars
        assert "customer.address.street" not in required_vars
        assert "customer.address.city" not in required_vars

    def test_field_names_returns_all_top_level_fields(self):
        """Test that field_names returns all top-level field names."""
        raw = ConstructBlueprintTestData.WITH_NESTED[1]
        blueprint = ConstructBlueprint.make_from_raw(raw)

        field_names = blueprint.field_names

        assert "invoice_number" in field_names
        assert "total" in field_names
        assert "billing_address" in field_names
        assert len(field_names) == 3


class TestConstructBlueprintRequiredVariables:
    """Tests for get_required_variables method edge cases."""

    def test_get_required_variables_filters_internal_variables(self):
        """Internal variables (_, place_holder) should be filtered out."""
        raw = {
            "output": {"template": "{{ _internal }} {{ place_holder }} {{ user_data }}"},
        }
        blueprint = ConstructBlueprint.make_from_raw(raw)
        required_vars = blueprint.get_required_variables()

        assert "user_data" in required_vars
        assert "_internal" not in required_vars
        assert "place_holder" not in required_vars

    def test_get_required_variables_fixed_only_returns_empty(self):
        """Construct with only fixed values requires no variables."""
        raw = {"title": "Fixed Title", "count": 42}
        blueprint = ConstructBlueprint.make_from_raw(raw)

        assert blueprint.get_required_variables() == set()


class TestConstructBlueprintValidation:
    """Tests for ConstructBlueprint validation."""

    def test_empty_construct_raises_error(self):
        """Empty construct should raise an error."""
        with pytest.raises(ValueError, match="empty"):
            ConstructBlueprint.make_from_raw({})
