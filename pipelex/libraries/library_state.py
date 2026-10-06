"""State tokens: a number naming one state of a library's contents, never reused.

A pipe or concept library takes a fresh token when it is created and again on every change to what it holds, so a value
derived from a library, such as the typed flow a PipeSequence builds from the pipes and concepts it resolves, can record
the tokens it was derived under and know it is stale once either differs. Tokens come from one process-wide counter, so
two libraries, or a library torn down and another created in its place, never share one.
"""

from itertools import count

_STATE_TOKENS = count(start=1)


def next_library_state_token() -> int:
    """A token no library state has had before in this process."""
    return next(_STATE_TOKENS)
