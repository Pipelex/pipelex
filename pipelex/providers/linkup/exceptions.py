from pipelex.cogt.exceptions import CogtError


class LinkupSearchResponseError(CogtError):
    """The Linkup API answered a structured search with a payload shape the leaf cannot validate."""
