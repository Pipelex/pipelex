from pipelex.types import StrEnum


class PortkeyHeaderKey(StrEnum):
    TRACE_ID = "x-portkey-trace-id"
    SPAN_ID = "x-portkey-span-id"
    SPAN_NAME = "x-portkey-span-name"
    CONFIG = "x-portkey-config"
    PROVIDER = "x-portkey-provider"


class PortkeyOpenAISdkVariant(StrEnum):
    PORTKEY_COMPLETIONS = "portkey_completions"
    PORTKEY_RESPONSES = "portkey_responses"

    @classmethod
    def is_completions(cls, sdk: str) -> bool:
        try:
            variant = cls(sdk)
        except ValueError:
            return False
        match variant:
            case cls.PORTKEY_COMPLETIONS:
                return True
            case cls.PORTKEY_RESPONSES:
                return False

    @classmethod
    def is_responses(cls, sdk: str) -> bool:
        try:
            variant = cls(sdk)
        except ValueError:
            return False
        match variant:
            case cls.PORTKEY_COMPLETIONS:
                return False
            case cls.PORTKEY_RESPONSES:
                return True
