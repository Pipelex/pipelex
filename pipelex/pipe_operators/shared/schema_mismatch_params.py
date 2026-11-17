"""The parameters of an answer that does not fit its concept, filled by the operator that asked for it.

`model.output_schema_mismatch` names the model and the concept the answer had to fit. The workers know the model,
which their chokepoints attribute, but never the concept: a worker is handed a schema class. The operator that ran the
generation holds the concept, the one resolved for this run, and the model it resolved, so it fills what the error
raised below it lacks.
"""

from collections.abc import Generator
from contextlib import contextmanager

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


@contextmanager
def filling_schema_mismatch_params(*, concept_ref: str, model_handle: str | None) -> Generator[None]:
    """Fill the concept, and the model when nothing names one, on an answer that does not fit, then let it go on.

    Wrapped around an operator's call that generates the answer and the `except` clauses that wrap its failures, so
    it sees both the errors that pass the operator unwrapped and the wrappers the operator raises from them. An error
    of any other code is left untouched, and so is a parameter the error whose code it reports already gave or holds.

    Args:
        concept_ref: The concept the answer had to fit, as resolved for this run.
        model_handle: The model the operator resolved, given only when no error along the chain names a model;
            ``None`` when the operator has none to give.

    Yields:
        Nothing: the wrapped block runs in its place.
    """
    try:
        yield
    except PipelexError as exc:
        if exc.resolve_error_code() == CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH:
            carrier = exc.code_carrier()
            carried = {**carrier.problem_params(), **carrier.given_params}
            if carried.get("concept") is None:
                exc.with_params(concept=concept_ref)
            if model_handle is not None and carried.get("model") is None and exc.chain_facts().model is None:
                exc.with_params(model=model_handle)
        raise
