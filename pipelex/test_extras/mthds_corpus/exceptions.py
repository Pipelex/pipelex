from pipelex.base_exceptions import PipelexError


class CorpusEntryError(PipelexError):
    """An entry directory that does not satisfy the layout the corpus contract pins."""
