from pipelex.types import StrEnum


class SpecialLibraryId(StrEnum):
    """Special library identifiers.

    UNTITLED: The untitled/default library
    TEST: The test library
    """

    UNTITLED = "untitled"
    TEST = "test"
