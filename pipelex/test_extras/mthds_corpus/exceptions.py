class CorpusEntryError(Exception):
    """An entry directory that does not satisfy the layout the corpus contract pins.

    Deliberately not a ``PipelexError``: error discovery excludes ``test_extras`` (see
    ``_FIXTURE_DIR_NAMES`` in ``pipelex/errors/error_class_discovery.py``), so a ``PipelexError``
    here would carry a wire identity that no snapshot gates and a class-derived ``type_uri`` that
    the uniqueness check never sees. This failure is a malformed fixture directory, which is
    nobody's wire contract.
    """
