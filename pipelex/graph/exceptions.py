"""GraphSpec-specific exceptions."""

from pipelex.base_exceptions import PipelexError


class GraphSpecError(PipelexError):
    """Base exception for GraphSpec-related errors."""


class GraphSpecValidationError(GraphSpecError):
    """Exception raised when GraphSpec validation fails.

    This includes invariant violations such as:
    - Missing nodes referenced by edges
    - Duplicate node IDs
    - Duplicate edge IDs
    - Failed status without error specification
    """
