from typing import Any

import jsonschema
import pytest

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.memory.exceptions import InputShapingError
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import build_input_specs

# (multiplicity, provided value) — every JSON type at each declaration, including the ones refused. Two shapes
# are left out because the two sides differ on them by design: a single bare value at `Anything[]`, which the
# shaper wraps into a one-item list, and an `Anything[]` item keyed exactly `concept` and `content`, which R10
# refuses and the schema does not state (`wip/anything-slot/plan.md` defers it).
AGREEMENT_CASES: list[tuple[VariableMultiplicity | None, Any]] = [
    (None, {}),
    (None, {"a": 1}),
    (None, "hi"),
    (None, ""),
    (None, 3),
    (None, 4.2),
    (None, 0),
    (None, True),
    (None, False),
    (None, None),
    (None, []),
    (None, ["a"]),
    (None, [{"a": 1}]),
    (True, []),
    (True, ["hi", 3, True, {"a": 1}]),
    (True, [[1]]),
    (True, [None]),
    (True, [["a"], "b"]),
    (2, ["hi", {"a": 1}]),
    (2, ["hi"]),
    (2, ["hi", None]),
]


class TestAnythingSchemaAgreement:
    @pytest.mark.parametrize(("multiplicity", "provided_value"), AGREEMENT_CASES)
    def test_the_schema_admits_exactly_what_the_shaper_takes(self, multiplicity: VariableMultiplicity | None, provided_value: Any) -> None:
        """R4: the published `Anything` schema and the input shaper accept and refuse the same JSON types."""
        input_specs = build_input_specs([("payload", "native.Anything", multiplicity)])
        stuff_spec = input_specs.root["payload"]
        rendered = stuff_spec.render_stuff_spec(concept_provider=get_concept_library(), output_format=ConceptRepresentationFormat.SCHEMA)
        json_schema = rendered["content"]

        # The `types-jsonschema` overloads of `is_valid` carry an `Unknown` arm.
        schema_admits = jsonschema.Draft202012Validator(json_schema).is_valid(provided_value)  # pyright: ignore[reportUnknownMemberType]
        try:
            InputShaper.shape({"payload": provided_value}, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)
            shaper_takes = True
        except InputShapingError:
            shaper_takes = False

        assert schema_admits == shaper_takes, (
            f"schema admits={schema_admits}, shaper takes={shaper_takes} for {provided_value!r} at multiplicity {multiplicity!r}: {json_schema}"
        )
