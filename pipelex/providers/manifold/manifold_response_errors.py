"""How a response body the service sent in an unexpected shape is described in an error message.

A local formatter rather than core's richer validation-error analysis, which is a general-purpose
helper rather than an extension point: a service response that fails its schema needs only which
fields were wrong and why.
"""

from pydantic import ValidationError


def describe_response_validation_error(*, exc: ValidationError) -> str:
    """One `location: message` clause per error, in the order pydantic reports them."""
    clauses = [f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}" for error in exc.errors()]
    return "; ".join(clauses)
