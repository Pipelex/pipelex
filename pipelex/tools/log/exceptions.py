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
