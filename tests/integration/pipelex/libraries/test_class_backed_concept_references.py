"""A structure field naming a concept backed by a Python class resolves to that class.

The generator spells a field's forward reference from the concept ref (`shop__Customer`), whatever class the
concept actually has, so the rebuild must find a class-backed concept under that spelling as well as under the
class's own name. And a Python class whose own rebuild fails is left to its module, never refusing the load.
"""

from collections.abc import Callable
from pathlib import Path

from pipelex.interpreter_hub import get_concept_library, get_library_manager

CUSTOMER_PAYLOAD_PY = """
from pipelex.core.stuffs.structured_content import StructuredContent


class InventedCustomerPayload(StructuredContent):
    name: str
"""

CLASS_BACKED_MTHDS = """
domain = "invented_shop"
description = "A concept backed by a Python class, held by an inline structure"

[concept.Customer]
description = "A customer"
structure = "InventedCustomerPayload"

[concept.Order]
description = "An order"

[concept.Order.structure]
customer = { type = "concept", concept_ref = "invented_shop.Customer", description = "The customer", required = true }
"""

# `weird` is typed by a plain class pydantic cannot build a schema for, so rebuilding it raises a
# `PydanticSchemaGenerationError`; the class was unusable before the rebuild, and stays the module's concern.
UNBUILDABLE_PY = """
from pipelex.core.stuffs.structured_content import StructuredContent


class InventedOpaqueThing:
    pass


class InventedUnbuildableRecord(StructuredContent):
    order: "invented_ledger__Entry | None" = None
    weird: InventedOpaqueThing | None = None
"""

UNBUILDABLE_MTHDS = """
domain = "invented_ledger"
description = "A concept backed by a Python class whose rebuild fails"

[concept.Record]
description = "A record"
structure = "InventedUnbuildableRecord"

[concept.Entry]
description = "An entry"

[concept.Entry.structure]
number = { type = "text", description = "The entry's number", required = true }
"""


class TestClassBackedConceptReferences:
    def test_field_naming_a_class_backed_concept_is_fully_defined(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        (tmp_path / "invented_customer_payload.py").write_text(CUSTOMER_PAYLOAD_PY, encoding="utf-8")
        (tmp_path / "shop.mthds").write_text(CLASS_BACKED_MTHDS, encoding="utf-8")

        library_id = load_empty_library()
        get_library_manager().load_libraries(library_id=library_id, library_dirs=[tmp_path])

        concept_library = get_concept_library()
        order_class = concept_library.get_structure_class(concept=concept_library.get_required_concept("invented_shop.Order"))
        order = order_class.model_validate({"customer": {"name": "Invented customer"}})
        assert order.model_dump()["customer"] == {"name": "Invented customer"}

    def test_python_class_whose_rebuild_fails_does_not_refuse_the_load(self, tmp_path: Path, load_empty_library: Callable[[], str]):
        (tmp_path / "invented_unbuildable_record.py").write_text(UNBUILDABLE_PY, encoding="utf-8")
        (tmp_path / "ledger.mthds").write_text(UNBUILDABLE_MTHDS, encoding="utf-8")

        library_id = load_empty_library()
        get_library_manager().load_libraries(library_id=library_id, library_dirs=[tmp_path])

        assert get_concept_library().get_required_concept("invented_ledger.Record").structure_class_name == "InventedUnbuildableRecord"
