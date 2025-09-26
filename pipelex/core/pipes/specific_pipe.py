from pipelex.types import StrEnum


class SpecificPipeCodesEnum(StrEnum):
    CONTINUE = "continue"
    # TODO: Implement the break pipe: It should enable to leave the current sequence.
    # BREAK = "break"


# TODO: Rethink this class. They are not pipes really.
class SpecificPipe:
    @staticmethod
    def is_continue(pipe_code: str) -> bool:
        try:
            enum_value = SpecificPipeCodesEnum(pipe_code)
        except ValueError:
            return False

        match enum_value:
            case SpecificPipeCodesEnum.CONTINUE:
                return True
            # case SpecificPipeCodesEnum.BREAK:  # Uncomment when BREAK is implemented
            #     return False
