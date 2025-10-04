from pipelex.types import StrEnum


class SpecialOutcome(StrEnum):
    FAIL = "fail"
    CONTINUE = "continue"
    # TODO: Implement the break pipe: It should enable to leave the current sequence.
    # BREAK = "break"

    @classmethod
    def value_list(cls) -> set[str]:
        return set(cls)

    @classmethod
    def is_continue(cls, outcome: str) -> bool:
        try:
            enum_value = SpecialOutcome(outcome)
        except ValueError:
            return False

        match enum_value:
            case SpecialOutcome.FAIL:
                return False
            case SpecialOutcome.CONTINUE:
                return True
            # case SpecificPipeCodesEnum.BREAK:  # Uncomment when BREAK is implemented
            #     return False
