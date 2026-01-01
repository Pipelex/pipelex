from pipelex.types import StrEnum


class InferenceOutputType(StrEnum):
    TEXT = "Text"
    OBJECT = "Object"
    IMAGE = "Image"
    PAGES = "Pages"

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
            case cls.IMAGE:
                return False
            case cls.PAGES:
                return False
