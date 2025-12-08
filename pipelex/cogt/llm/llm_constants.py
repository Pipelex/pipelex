from pipelex.types import StrEnum


class LLMOutputType(StrEnum):
    TEXT = "Text"
    OBJECT = "Object"

    @classmethod
    def is_text(cls, output_desc: str) -> bool:
        try:
            output_desc_enum = cls(output_desc)
        except ValueError:
            return False
        match output_desc_enum:
            case cls.TEXT:
                return True
            case cls.OBJECT:
                return False
