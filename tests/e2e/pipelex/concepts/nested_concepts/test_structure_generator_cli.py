# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""E2E test for structures codegen (the `build structures` engine) with nested concepts.

This test verifies that:
1. The codegen engine (`codegen types --target python-structures`, which `pipelex build structures`
   aliases) emits a single importable module for nested concepts
2. The generated module is importable as-is (no manual forward-ref plumbing)
3. The generated classes can be instantiated and used
4. Concept-to-concept references (nested and list-nested) resolve correctly

Note: pyright checks are disabled for this file because we dynamically import
and instantiate generated classes at runtime.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.codegen.emission import write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.method_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.execution_seams import load_libraries_and_activate


class TestStructureGeneratorCLI:
    """E2E: the structures projection over a real bundle with nested concept references."""

    def test_generate_and_import_nested_concept_structures(self):
        """The emitted structures.py imports cleanly and its nested classes compose.

        This test:
        1. Resolves the existing nested_concepts.mthds bundle into a normalized crate
        2. Emits the python-structures projection through the stamped write path
        3. Dynamically imports the generated module
        4. Instantiates the generated classes, nesting Customer and LineItem inside Invoice
        """
        bundle_dir = Path("tests/e2e/pipelex/concepts/nested_concepts").resolve()
        assert (bundle_dir / "nested_concepts.mthds").exists()

        library_manager = get_library_manager()
        previous_library_id = get_current_library_id_or_none()
        resolve_library_id = load_libraries_and_activate([bundle_dir])
        try:
            crate = library_manager.get_crate(resolve_library_id)
            assert crate is not None
            normalized = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
        finally:
            if previous_library_id is not None:
                set_current_library(library_id=previous_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=resolve_library_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_directory = Path(temp_dir)
            emitted = emit_types(normalized, target=CodegenTarget.PYTHON_STRUCTURES)
            report = write_stamped_projection(
                emitted,
                output_dir=output_directory,
                crate_fingerprint=normalized.fingerprint,
                engine_version="test",
                kind=CodegenKind.TYPES,
                target=CodegenTarget.PYTHON_STRUCTURES,
            )
            assert report.written == ["structures.py"]
            assert (output_directory / CODEGEN_LOCK_FILENAME).is_file()

            structures_file = output_directory / "structures.py"
            structures_code = structures_file.read_text(encoding="utf-8")

            # Bare-when-unique class names (no cross-domain collision in this closure)
            assert "class LineItem(StructuredContent):" in structures_code
            assert "class Customer(StructuredContent):" in structures_code
            assert "class Invoice(StructuredContent):" in structures_code

            # The single module imports as-is: forward references resolve within it.
            # It must stay in sys.modules while in use — pydantic resolves the
            # `from __future__ import annotations` forward refs lazily at first instantiation.
            module = self._import_module_from_file(structures_file)
            try:
                self._exercise_generated_classes(module)
            finally:
                sys.modules.pop(module.__name__, None)

    def _exercise_generated_classes(self, module: Any) -> None:
        line_item_class: Any = module.LineItem
        customer_class: Any = module.Customer
        invoice_class: Any = module.Invoice

        line_item = line_item_class(product_name="Widget", quantity=3, unit_price=10.0)
        assert line_item.product_name == "Widget"
        assert line_item.quantity == 3
        assert line_item.unit_price == 10.0

        customer = customer_class(name="John Smith", email="john@example.com")
        assert customer.name == "John Smith"
        assert customer.email == "john@example.com"

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

    def _import_module_from_file(self, file_path: Path) -> Any:
        """Dynamically import a module from a Python file (left in sys.modules — caller cleans up)."""
        module_name = f"test_module_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        assert spec is not None, f"Could not load spec for {file_path}"
        assert spec.loader is not None, f"Spec has no loader for {file_path}"

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        return module
