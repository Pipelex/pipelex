from pipelex.cogt.exceptions import CogtError


class LinkupError(CogtError):
    """Base for every error this backend raises, so callers can catch the provider as a family."""


class LinkupSearchResponseError(LinkupError):
    """The Linkup API answered a structured search with a payload shape the leaf cannot validate."""


class LinkupSearchEmptyResultError(LinkupError):
    """The Linkup API answered a structured search with no object payload to fill the output structure."""
