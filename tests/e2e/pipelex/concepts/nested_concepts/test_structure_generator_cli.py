# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""E2E test for the structure generator CLI with nested concepts.

This test verifies that:
1. `pipelex build structures` generates valid Python files for nested concepts
2. The generated files are importable
3. The generated classes can be instantiated and used
4. Forward references between nested concepts are properly handled

Note: pyright checks are disabled for this file because we dynamically import
and instantiate generated classes at runtime.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pipelex.cli.commands.build.structures_cmd import generate_structures_from_blueprints
from pipelex.pipeline.validate_bundle import validate_bundle


@pytest.mark.asyncio
class TestStructureGeneratorCLI:
    """E2E tests for structure generation CLI with nested concepts."""

    async def test_generate_and_import_nested_concept_structures(self):
        """Test that generated structure files for nested concepts are importable and usable.

        This test:
        1. Uses the existing nested_concepts.mthds file with concept-to-concept references
        2. Generates Python structure files via the CLI helper function
        3. Dynamically imports the generated modules
        4. Instantiates the generated classes
        5. Verifies nested concept references work correctly
        """
        # Path to the MTHDS file with nested concepts
        mthds_file_path = Path("tests/e2e/pipelex/concepts/nested_concepts/nested_concepts.mthds").resolve()
        assert mthds_file_path.exists(), f"MTHDS file not found: {mthds_file_path}"

        # Create a temporary directory for generated structures
        with tempfile.TemporaryDirectory() as temp_dir:
            output_directory = Path(temp_dir)

            # Validate the MTHDS file to get blueprints
            validate_result = await validate_bundle(mthds_file_path=mthds_file_path)
            blueprints = validate_result.blueprints

            # Generate structure files
            generated_files = generate_structures_from_blueprints(
                blueprints=blueprints,
                output_directory=output_directory,
                skip_existing_check=True,
            )

            # Verify files were generated
            assert len(generated_files) >= 3, f"Expected at least 3 generated files, got {len(generated_files)}"

            # Find the generated files
            line_item_file = output_directory / "nested_concepts_test__line_item.py"
            customer_file = output_directory / "nested_concepts_test__customer.py"
            invoice_file = output_directory / "nested_concepts_test__invoice.py"

            assert line_item_file.exists(), f"LineItem structure file not generated: {line_item_file}"
            assert customer_file.exists(), f"Customer structure file not generated: {customer_file}"
            assert invoice_file.exists(), f"Invoice structure file not generated: {invoice_file}"

            # Read and verify the generated code contains proper structure.
            # Class names are domain-qualified (e.g. "nested_concepts_test__LineItem") so
            # they match what ConceptFactory registers in the class registry.
            line_item_code = line_item_file.read_text()
            customer_code = customer_file.read_text()
            invoice_code = invoice_file.read_text()

            line_item_class_name = "nested_concepts_test__LineItem"
            customer_class_name = "nested_concepts_test__Customer"
            invoice_class_name = "nested_concepts_test__Invoice"

            assert f"class {line_item_class_name}(StructuredContent):" in line_item_code
            assert f"class {customer_class_name}(StructuredContent):" in customer_code
            assert f"class {invoice_class_name}(StructuredContent):" in invoice_code

            # Verify Invoice has forward references to the qualified Customer and LineItem names
            assert customer_class_name in invoice_code
            assert line_item_class_name in invoice_code

            # Dynamically import the generated modules
            # Import order matters: dependencies first
            line_item_class = self._import_class_from_file(line_item_file, line_item_class_name)
            customer_class = self._import_class_from_file(customer_file, customer_class_name)

            # Now import Invoice - it has forward references to LineItem and Customer
            # We need to add LineItem and Customer to the namespace for forward reference resolution
            invoice_spec = importlib.util.spec_from_file_location("invoice_module", invoice_file)
            assert invoice_spec is not None
            assert invoice_spec.loader is not None
            invoice_module = importlib.util.module_from_spec(invoice_spec)

            # Add the dependencies to the module's globals for forward reference resolution
            invoice_module.__dict__[line_item_class_name] = line_item_class
            invoice_module.__dict__[customer_class_name] = customer_class

            sys.modules["invoice_module"] = invoice_module
            invoice_spec.loader.exec_module(invoice_module)
            invoice_class: Any = getattr(invoice_module, invoice_class_name)

            # Rebuild the model to resolve forward references
            invoice_class.model_rebuild(
                _types_namespace={
                    line_item_class_name: line_item_class,
                    customer_class_name: customer_class,
                }
            )

            # Instantiate the classes to verify they work
            line_item = line_item_class(
                product_name="Widget",
                quantity=3,
                unit_price=10.0,
            )
            assert line_item.product_name == "Widget"
            assert line_item.quantity == 3
            assert line_item.unit_price == 10.0

            customer = customer_class(
                name="John Smith",
                email="john@example.com",
            )
            assert customer.name == "John Smith"
            assert customer.email == "john@example.com"

            # Create Invoice with nested concepts
            invoice = invoice_class(
                invoice_number="INV-001",
                customer=customer,
                line_items=[line_item],
                total_amount=30.0,
            )
            assert invoice.invoice_number == "INV-001"
            assert invoice.customer.name == "John Smith"
            assert len(invoice.line_items) == 1
            assert invoice.line_items[0].product_name == "Widget"
            assert invoice.total_amount == 30.0

            # Clean up imported modules
            sys.modules.pop("invoice_module", None)

    def _import_class_from_file(self, file_path: Path, class_name: str) -> Any:
        """Dynamically import a class from a Python file.

        Args:
            file_path: Path to the Python file
            class_name: Name of the class to import

        Returns:
            The imported class
        """
        module_name = f"test_module_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        assert spec is not None, f"Could not load spec for {file_path}"
        assert spec.loader is not None, f"Spec has no loader for {file_path}"

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        the_class: Any = getattr(module, class_name)
        return the_class
