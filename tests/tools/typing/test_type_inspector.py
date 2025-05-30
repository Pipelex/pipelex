from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.tools.typing.type_inspector import get_type_structure


class Simple(BaseModel):
    """A simple class that references itself."""

    field_1: int
    field_2: "Simple"


def test_self_referencing_class_no_loop():
    """Test that get_type_structure handles self-referencing classes without infinite loops."""
    # Prepare test data
    TestClass = Simple
    TestClass.model_rebuild()

    # Call the function
    structure = get_type_structure(TestClass, base_class=BaseModel)
    pretty_print(structure, title="Structure")

    # Assert the result
    assert len(structure) > 0, "Structure should not be empty"
    assert structure.count("Class 'Simple':") == 1, "Class should only appear once"
    assert any("field_2" in line and "Simple" in line for line in structure), "Structure should show next field with self-reference"
