from typing import ClassVar


class ProblemViewsTestData:
    OPERATOR_MESSAGE: ClassVar[str] = "The backend 'acme' has no api_key in /etc/pipelex/backends.toml"
    COMPONENT: ClassVar[str] = "inference backend acme"
    GATEWAY_MESSAGE: ClassVar[str] = "The gateway refused the call; see its message for the integration"
    GATEWAY_PROVIDER_TEXT: ClassVar[str] = "integration 'acme-prod' is disabled: set ACME_PROD_KEY and ACME_PROD_URL"
    # Phrases that send a reader to a text a view may withhold: the error's own message or the provider's.
    HIDDEN_TEXT_PHRASES: ClassVar[tuple[str, ...]] = (
        "error message",
        "its message",
        "own message",
        "the message",
        "provider's message",
        "see the message",
    )
