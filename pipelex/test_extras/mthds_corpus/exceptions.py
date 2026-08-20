class CorpusEntryError(Exception):
    """An entry directory that does not satisfy the layout the corpus contract pins.

    Deliberately not a ``PipelexError``: error discovery excludes ``test_extras`` (see
    ``_FIXTURE_DIR_NAMES`` in the error-pages generator), so a ``PipelexError`` here would carry a
    ``type_uri`` pointing at a documentation page nothing generates, and a wire identity no
    snapshot gates. This failure is a malformed fixture directory, which is nobody's wire contract.
    """
