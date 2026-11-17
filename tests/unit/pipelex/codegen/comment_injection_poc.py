"""The proof of concept of the codegen comment injection, shared by the tests of each layer that now stops it.

The proof of concept is a bundle whose dict `value_type` or list `item_type` holds a line break followed by a statement.
Before the fix, the Python emitters quoted the name raw into the field's `# imprecise:` comment, the line break ended the
comment, and importing the emitted module ran the statement.
"""

import io
import json
import sys
import tokenize
from pathlib import Path
from types import ModuleType

import pytest

from pipelex.codegen.emitters.target import CodegenTarget
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from tests.unit.pipelex.codegen.conftest import CRATE_TEST_VERSION

PYTHON_TARGETS = [
    pytest.param(CodegenTarget.PYTHON_PYDANTIC, id="python-pydantic"),
    pytest.param(CodegenTarget.PYTHON_STRUCTURES, id="python-structures"),
]

# The two line breaks the proof of concept used: both end a line of Python source, so both ended the comment.
LINE_BREAKS = [pytest.param("\n", id="line-feed"), pytest.param("\r", id="carriage-return")]

# The nested type positions an author writes a type name in.
NESTED_POSITIONS = [pytest.param("value_type", id="dict-value-type"), pytest.param("item_type", id="list-item-type")]


def poc_payload(*, line_break: str, marker: Path) -> str:
    """The proof of concept's type name: a line break, a statement writing `marker`, and a `#` swallowing the rest."""
    return f"x{line_break}    __import__('pathlib').Path({str(marker)!r}).write_text('pwned'){line_break}    #"


def poc_field(*, position: str, type_name: str) -> dict[str, str]:
    """The structure field of the proof of concept, a dict or a list whose nested type name is `type_name`."""
    if position == "value_type":
        return {"type": "dict", "key_type": "text", "value_type": type_name, "description": "meta"}
    return {"type": "list", "item_type": type_name, "description": "tags"}


def poc_bundle(*, position: str, type_name: str) -> str:
    """The proof-of-concept bundle, its field written as an inline table with the name as a TOML basic string."""
    field = poc_field(position=position, type_name=type_name)
    # A JSON string is a TOML basic string for every character this payload holds.
    inline_table = ", ".join(f"{key} = {json.dumps(value)}" for key, value in field.items())
    header = 'domain = "poc"\ndescription = "PoC"\n\n[concept.Thing]\ndescription = "A thing"\n\n'
    return f"{header}[concept.Thing.structure]\nfield = {{ {inline_table} }}\n"


def crate_around_validation(*, position: str, type_name: str) -> LibraryCrate:
    """A crate holding the proof-of-concept field, built around the load refusal, to reach the layers behind it."""
    field = ConceptStructureBlueprint.model_construct(
        description="a field",
        type=ConceptStructureBlueprintFieldType.DICT if position == "value_type" else ConceptStructureBlueprintFieldType.LIST,
        key_type="text" if position == "value_type" else None,
        value_type=type_name if position == "value_type" else None,
        item_type=type_name if position == "item_type" else None,
        concept_ref=None,
        item_concept_ref=None,
        choices=None,
        default_value=None,
        required=False,
        hints=None,
    )
    concept = ConceptBlueprint.model_construct(description="A thing", structure={"field": field}, refines=None)
    authored = LibraryCrate(concepts={"poc.Thing": concept}, domains={"poc": DomainBlueprint(code="poc", description="PoC")})
    return normalize_crate(authored, mthds_version=CRATE_TEST_VERSION)


def code_names(content: str) -> set[str]:
    """Every name the module's code holds, read by Python's own tokenizer: a name inside a comment or a string is none."""
    return {token.string for token in tokenize.generate_tokens(io.StringIO(content).readline) if token.type == tokenize.NAME}


def import_emitted(*, content: str, module_name: str) -> ModuleType:
    """Import an emitted module the way a developer's app does, so any statement in it runs."""
    module = ModuleType(module_name)
    sys.modules[module_name] = module
    try:
        exec(compile(content, f"<{module_name}>", "exec"), module.__dict__)
    finally:
        del sys.modules[module_name]
    return module
