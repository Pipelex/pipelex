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
