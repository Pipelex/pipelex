from pipelex.types import StrEnum


class GatewayOpenAISdkVariant(StrEnum):
    GATEWAY_COMPLETIONS = "gateway_completions"
    GATEWAY_RESPONSES = "gateway_responses"

    @classmethod
    def is_completions(cls, sdk: str) -> bool:
        try:
            variant = cls(sdk)
        except ValueError:
            return False
        match variant:
            case cls.GATEWAY_COMPLETIONS:
                return True
            case cls.GATEWAY_RESPONSES:
                return False

    @classmethod
    def is_responses(cls, sdk: str) -> bool:
        try:
            variant = cls(sdk)
        except ValueError:
            return False
        match variant:
            case cls.GATEWAY_COMPLETIONS:
                return False
            case cls.GATEWAY_RESPONSES:
                return True
