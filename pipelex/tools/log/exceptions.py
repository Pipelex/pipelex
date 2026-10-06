from pipelex.base_exceptions import ErrorDomain
from pipelex.system.exceptions import CredentialsError


class GcpLogSinkCredentialsError(CredentialsError):
    """Raised at boot when the ``gcp`` log sink's credentials cannot be found or are refused when refreshed.

    Every record the sink would export is lost without them, so the boot stops rather than running a
    process whose logs go nowhere. Fixed by an operator renewing the credentials or selecting another
    sink, not by the caller correcting input.
    """

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Log sink credentials missing or refused"


class LogSinkVariableError(CredentialsError):
    """Raised at boot when a ``${…}`` placeholder in a log sink's settings does not resolve.

    The ``otlp`` sink's header values and the ``gcp`` sink's key path are read through the secrets
    provider, and a placeholder left as written would be sent to the collector, or opened as a path, as
    if it were the credential: every record the sink exports would be refused on its export thread
    while the boot reported success. So the boot stops instead, naming the section, the key and the
    variable, never a value. Fixed by an operator setting the variable or selecting another sink.
    """

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Log sink variable did not resolve"

    def __init__(self, *, sink_method: str, section: str, key: str, variable: str, cause: str):
        self.sink_method = sink_method
        self.section = section
        self.key = key
        self.variable = variable
        msg = (
            f"The '{sink_method}' log sink cannot be built: `{key}` under [{section}] names the variable "
            f"'${{{variable}}}', which did not resolve ({cause}). Set it in the secrets provider that "
            "[runtime.secrets] selects, or in the environment for an `env:` variable, or select the 'json' sink in [runtime.log]."
        )
        super().__init__(msg)


class LogSinkHeaderValueError(CredentialsError):
    """Raised at boot when an ``otlp`` sink header value holds a line break once its placeholders resolve.

    No HTTP header can carry a line break, so the exporter would be built and installed, then refuse every
    batch on its export thread, where the sink drops its own failures, while the boot reported success. A
    secret read from a file often ends with a newline, which is how one gets there. So the boot stops
    instead, naming the section and the key, never the value. Fixed by an operator storing the secret
    without the line break.
    """

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Log sink header value holds a line break"

    def __init__(self, *, sink_method: str, section: str, key: str):
        self.sink_method = sink_method
        self.section = section
        self.key = key
        msg = (
            f"The '{sink_method}' log sink cannot be built: `{key}` under [{section}] holds a line break once its "
            "placeholders resolve, and no HTTP header can carry one, so the collector would receive nothing. A secret "
            "read from a file often ends with a newline: store it without one, in the secrets provider that [runtime.secrets] selects."
        )
        super().__init__(msg)
