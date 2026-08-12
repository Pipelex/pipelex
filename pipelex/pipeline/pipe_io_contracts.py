"""Per-pipe input/output contracts (`pipe_io_contracts`) for the validate surfaces.

This is the canonical builder for the `pipe_io_contracts` artifact reported by the MTHDS
Protocol `validate` operation (local runtime and hosted API alike). It projects loaded
pipes into typed `PipeIOContract` entries — for each pipe, the JSON-Schema view of its
declared inputs and the concept/multiplicity of its output — keyed by the namespaced
`pipe_ref` (`domain.code`), the one identity convention shared by every validate artifact
(`validated_pipes`, `pending_signatures`).

Callers must invoke the builder against loaded pipes INSIDE the validation library's
window, before teardown — the builder now says so itself rather than degrading. It asks
the interpreter hub for the loaded method's concept library up front, so a post-teardown
call raises instead of quietly rendering against whatever the class registry last held.

That silent-stale reading used to be the hazard this note warned about: bundle-defined
structure classes are registered in the process-global registry during library load and
are never unregistered (the registry has no unregister mechanism), so the classes outlive
the library that defined them. They still do — what changed is that this builder no longer
reaches them behind the library's back. (Registry teardown hygiene is tracked separately.)
"""

from enum import StrEnum
from typing import Any, Sequence

from pydantic import BaseModel, Field, PydanticUndefinedAnnotation, PydanticUserError

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.exceptions import PipeIOContractError


class IOMultiplicity(StrEnum):
    """Wire value for an output's multiplicity: one item, or a list of them.

    Any multiple output — variable-length or fixed-count — reports `variable`; the
    distinction the contract carries is "one vs many", not the exact count.
    """

    SINGLE = "single"
    VARIABLE = "variable"


class PipeInputContract(BaseModel):
    """One declared input: the concept it expects and the JSON Schema of its content."""

    concept_ref: str
    optional: bool = False
    """`True` when the input is declared optional (`?`): the caller may omit it and the pipe
    handles absence itself. A plain or force (`!`) input reports `False` — it must be provided."""

    json_schema: dict[str, Any] = Field(default_factory=dict)


class PipeOutputContract(BaseModel):
    """The pipe's output: the concept it produces and whether it is one item or a list."""

    concept_ref: str
    multiplicity: IOMultiplicity
    optional: bool = False
    """`True` when the output is declared optional (`?`): the pipe may resolve it as a recorded
    absence instead of a value — a successful run with an absent result."""


class PipeIOContract(BaseModel):
    """The input/output contract of one pipe — a `pipe_io_contracts` entry."""

    inputs: dict[str, PipeInputContract] = Field(default_factory=dict)
    output: PipeOutputContract


def build_pipe_io_contracts(pipes: Sequence[PipeAbstract]) -> dict[str, PipeIOContract]:
    """Project loaded pipes into `pipe_io_contracts` entries keyed by namespaced `pipe_ref`.

    Works on any loaded `PipeAbstract` — including `PipeSignature` placeholders, whose
    declared contract is exactly what a top-down build needs to see. Must run while the
    validation library is still loaded: the concept library is resolved from the current
    library up front, so a post-teardown call raises rather than rendering against stale
    classes (see the module docstring).

    Args:
        pipes: The loaded pipes to project (typically `ValidateBundleResult.pipes`).

    Returns:
        `pipe_ref` → `PipeIOContract` for every given pipe.

    Raises:
        PipeIOContractError: When a pipe input's JSON-Schema rendering fails — a pydantic
            schema-generation error on a structure class, a structure class missing from
            the registry (`ConceptValueError`), or a render-shape drift — converted here
            so every validate surface reports the same structured error.
    """
    # Per-call memo: pipes routinely share input concepts, and the JSON-Schema rendering
    # (pydantic's model_json_schema, uncached) would otherwise be regenerated once per
    # occurrence. Deliberately NOT a module-level cache — bundle-defined structure classes
    # vary per loaded library, so a cross-call cache would serve stale schemas.
    schema_memo: dict[tuple[str, bool], dict[str, Any]] = {}
    concept_provider = get_concept_library()
    io_contracts: dict[str, PipeIOContract] = {}
    for pipe in pipes:
        pipe_inputs: dict[str, PipeInputContract] = {}
        for var_name, stuff_spec in pipe.inputs.root.items():
            memo_key = (stuff_spec.concept.concept_ref, stuff_spec.is_multiple())
            json_schema = schema_memo.get(memo_key)
            if json_schema is None:
                try:
                    # Indexing (not .get with a default) is deliberate: a render-shape drift
                    # must surface as the structured error below, never ship a silently
                    # empty schema on the wire.
                    json_schema = stuff_spec.render_stuff_spec(concept_provider=concept_provider, output_format=ConceptRepresentationFormat.SCHEMA)[
                        "content"
                    ]
                except (ConceptValueError, KeyError, PydanticUserError, PydanticUndefinedAnnotation) as exc:
                    msg = (
                        f"Failed to render the JSON Schema for input '{var_name}' of pipe "
                        f"'{pipe.pipe_ref}' (concept '{stuff_spec.concept.concept_ref}'): {exc}"
                    )
                    raise PipeIOContractError(message=msg) from exc
                schema_memo[memo_key] = json_schema
            pipe_inputs[var_name] = PipeInputContract(
                concept_ref=stuff_spec.concept.concept_ref,
                optional=stuff_spec.presence.is_optional,
                json_schema=json_schema,
            )
        pipe_output = PipeOutputContract(
            concept_ref=pipe.output.concept.concept_ref,
            multiplicity=IOMultiplicity.VARIABLE if pipe.output.is_multiple() else IOMultiplicity.SINGLE,
            optional=pipe.output.presence.is_optional,
        )
        io_contracts[pipe.pipe_ref] = PipeIOContract(inputs=pipe_inputs, output=pipe_output)
    return io_contracts
