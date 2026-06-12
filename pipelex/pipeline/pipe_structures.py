"""Per-pipe input/output contracts (`pipe_structures`) for the validate surfaces.

This is the canonical builder for the `pipe_structures` artifact reported by the MTHDS
Protocol `validate` operation (local runtime and hosted API alike). It projects loaded
pipes into typed `PipeIOContract` entries — for each pipe, the JSON-Schema view of its
declared inputs and the concept/multiplicity of its output — keyed by the namespaced
`pipe_ref` (`domain.code`), the one identity convention shared by every validate artifact
(`validated_pipes`, `pending_signatures`).

The JSON-Schema rendering resolves each concept's structure class through the class
registry, which holds bundle-defined structure classes only while the validation library
is loaded — so callers must invoke the builder against loaded pipes BEFORE tearing the
validation library down.
"""

from typing import Any, Sequence

from pydantic import BaseModel, Field

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.types import StrEnum


class IOMultiplicity(StrEnum):
    """Wire value for an output's multiplicity: one item, or a list of them.

    Any multiple output — variable-length or fixed-count — reports `variable`; the
    distinction the contract carries is "one vs many", not the exact count.
    """

    SINGLE = "single"
    VARIABLE = "variable"


class PipeInputContract(BaseModel):
    """One declared input: the concept it expects and the JSON Schema of its content."""

    concept_code: str
    json_schema: dict[str, Any] = Field(default_factory=dict)


class PipeOutputContract(BaseModel):
    """The pipe's output: the concept it produces and whether it is one item or a list."""

    concept_code: str
    multiplicity: IOMultiplicity


class PipeIOContract(BaseModel):
    """The input/output contract of one pipe — a `pipe_structures` entry."""

    inputs: dict[str, PipeInputContract] = Field(default_factory=dict)
    output: PipeOutputContract


def build_pipe_structures(pipes: Sequence[PipeAbstract]) -> dict[str, PipeIOContract]:
    """Project loaded pipes into `pipe_structures` entries keyed by namespaced `pipe_ref`.

    Works on any loaded `PipeAbstract` — including `PipeSignature` placeholders, whose
    declared contract is exactly what a top-down build needs to see. Must run while the
    validation library is still loaded (bundle-defined structure classes resolve through
    the class registry).

    Args:
        pipes: The loaded pipes to project (typically `ValidateBundleResult.pipes`).

    Returns:
        `pipe_ref` → `PipeIOContract` for every given pipe.
    """
    structures: dict[str, PipeIOContract] = {}
    for pipe in pipes:
        pipe_inputs: dict[str, PipeInputContract] = {}
        for var_name, stuff_spec in pipe.inputs.root.items():
            schema_repr = stuff_spec.render_stuff_spec(ConceptRepresentationFormat.SCHEMA)
            pipe_inputs[var_name] = PipeInputContract(
                concept_code=schema_repr.get("concept", ""),
                json_schema=schema_repr.get("content", {}),
            )
        pipe_output = PipeOutputContract(
            concept_code=pipe.output.concept.concept_ref,
            multiplicity=IOMultiplicity.VARIABLE if pipe.output.is_multiple() else IOMultiplicity.SINGLE,
        )
        structures[pipe.pipe_ref] = PipeIOContract(inputs=pipe_inputs, output=pipe_output)
    return structures
