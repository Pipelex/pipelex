from pipelex.types import StrEnum


class PortkeyHeaderKey(StrEnum):
    TRACE_ID = "x-portkey-trace-id"
    SPAN_ID = "x-portkey-span-id"
    SPAN_NAME = "x-portkey-span-name"
    CONFIG = "x-portkey-config"


class PortkeyEnvVar(StrEnum):
    FORCE_PORTKEY_DEBUG = "FORCE_PORTKEY_DEBUG"
    FORCE_PORTKEY_TRACING = "FORCE_PORTKEY_TRACING"


class PortkeyOpenAISdkVariant(StrEnum):
    PORTKEY_COMPLETIONS = "portkey_completions"
    PORTKEY_RESPONSES = "portkey_responses"
