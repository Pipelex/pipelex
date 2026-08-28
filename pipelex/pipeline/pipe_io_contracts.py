"""Per-pipe input/output contracts (`pipe_io_contracts`) for the validate surfaces.

This is the reference builder for the `pipe_io_contracts` artifact reported by the MTHDS
Protocol `validate` operation (local runtime and hosted API alike). It projects loaded
pipes into typed `PipeIOContract` entries — for each pipe, the JSON-Schema view of its
declared inputs and the concept/multiplicity of its output — keyed by the namespaced
`pipe_ref` (`domain.code`), the one identity convention shared by every validate artifact
(`validated_pipes`, `pending_signatures`).

**The wire shapes belong to the standard, not to this engine.** `IOMultiplicity`,
`PipeInputContract`, `PipeOutputContract` and `PipeIOContract` are the models of
`mthds.protocol.pipe_io_contracts`, mirroring the standard's `pipe-io-contracts` page;
they are imported and re-exported here so this module keeps its callers, and this engine
holds no second declaration of them. What stays here is the projection: how a loaded pipe
becomes a contract. The models are closed shapes that check their own cross-field
invariants at construction, so a projection that ever drifted from the standard fails
here, at the derivation, rather than silently on the wire.

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

from typing import Any, Sequence

from mthds.protocol.pipe_io_contracts import IOMultiplicity, PipeInputContract, PipeIOContract, PipeIOContracts, PipeOutputContract
from pydantic import PydanticUndefinedAnnotation, PydanticUserError

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, fixed_item_count, is_multiple_multiplicity
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.exceptions import PipeIOContractError

__all__ = [
    "IOMultiplicity",
    "PipeIOContract",
    "PipeIOContracts",
    "PipeInputContract",
    "PipeOutputContract",
    "build_pipe_io_contracts",
    "make_io_multiplicity",
]


def make_io_multiplicity(*, multiplicity: VariableMultiplicity | None) -> tuple[IOMultiplicity, int | None]:
    """Project a declared multiplicity onto the wire pair (`multiplicity`, `item_count`).

    `item_count` is set exactly when the projection is `fixed`. `[1]` projects to `single`,
    like everywhere else in the chain.
    """
    item_count = fixed_item_count(multiplicity=multiplicity)
    if item_count is not None:
        return IOMultiplicity.FIXED, item_count
    if is_multiple_multiplicity(multiplicity=multiplicity):
        return IOMultiplicity.VARIABLE, None
    return IOMultiplicity.SINGLE, None


def build_pipe_io_contracts(pipes: Sequence[PipeAbstract]) -> PipeIOContracts:
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
    # The key normalizes multiplicity into (is_multiple, fixed_count) rather than carrying the
    # raw bool|int value: `hash(True) == hash(1)`, so a raw key would collide `Concept[]` with
    # `Concept[1]` and serve one's schema for the other.
    schema_memo: dict[tuple[str, bool, int | None], dict[str, Any]] = {}
    concept_provider = get_concept_library()
    io_contracts: PipeIOContracts = {}
    for pipe in pipes:
        pipe_inputs: dict[str, PipeInputContract] = {}
        for var_name, stuff_spec in pipe.inputs.root.items():
            memo_key = (
                stuff_spec.concept.concept_ref,
                stuff_spec.is_multiple(),
                fixed_item_count(multiplicity=stuff_spec.multiplicity),
            )
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
            input_multiplicity, input_item_count = make_io_multiplicity(multiplicity=stuff_spec.multiplicity)
            pipe_inputs[var_name] = PipeInputContract(
                concept_ref=stuff_spec.concept.concept_ref,
                presence=stuff_spec.presence,
                multiplicity=input_multiplicity,
                item_count=input_item_count,
                json_schema=json_schema,
            )
        output_multiplicity, output_item_count = make_io_multiplicity(multiplicity=pipe.output.multiplicity)
        pipe_output = PipeOutputContract(
            concept_ref=pipe.output.concept.concept_ref,
            multiplicity=output_multiplicity,
            item_count=output_item_count,
            optional=pipe.output.presence.is_optional,
        )
        io_contracts[pipe.pipe_ref] = PipeIOContract(inputs=pipe_inputs, output=pipe_output)
    return io_contracts
