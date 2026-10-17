from typing import Any, ClassVar


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

    # A problem whose code no registry of this process holds, as a newer worker or a stored record carries it, built in
    # the operator's view: its step and its diagnostics name a file of the host that a caller must never read.
    PRIVATE_HOST_FILE: ClassVar[str] = "/srv/pipelex/private/settings.toml"
    UNKNOWN_OPERATOR_CODE: ClassVar[str] = "pipelex.config.future_setting_missing"
    UNKNOWN_METHOD_CODE: ClassVar[str] = "method.future_fault"
    UNKNOWN_OPERATOR_PROBLEM: ClassVar[dict[str, Any]] = {
        "type": "https://docs.pipelex.com/errors/pipelex.config.future_setting_missing",
        "title": "A setting the runtime needs is missing",
        "detail": "A setting the runtime needs is missing.",
        "code": "pipelex.config.future_setting_missing",
        "domain": "operator",
        "retry": "no",
        "next_step": {"kind": "fix_configuration", "detail": "Set the setting in '/srv/pipelex/private/settings.toml', then restart the runtime."},
        "diagnostics": {"error_class": "FutureSettingError", "message": "no setting in /srv/pipelex/private/settings.toml"},
    }
    UNKNOWN_METHOD_PROBLEM: ClassVar[dict[str, Any]] = {
        "type": "https://mthds.ai/errors/method.future_fault",
        "title": "The method breaks a rule this runtime does not know",
        "detail": "The method breaks a rule.",
        "code": "method.future_fault",
        "domain": "method",
        "retry": "no",
        "next_step": {"kind": "change_method", "detail": "Correct the rule the host's '/srv/pipelex/private/settings.toml' enforces."},
    }
