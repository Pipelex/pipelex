from enum import StrEnum


class PipeRunParamKey(StrEnum):
    """The reserved keys of a pipe run's free-form `params` mapping.

    Every member starts with an underscore, which is what `PipeRunParams` validates on and what makes
    the set safely enumerable as reserved names: `ConceptStructureBlueprint` excludes them from the
    field names a method may declare.
    """

    DYNAMIC_OUTPUT_CONCEPT = "_dynamic_output_concept"
    NB_OUTPUT = "_nb_output"

    @classmethod
    def value_list(cls) -> list[str]:
        return [member.value for member in cls]
