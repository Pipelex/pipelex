from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import SecurityError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class SsrfBlockedError(SecurityError):
    """Raised when an outbound request is refused because the destination host
    resolved to a disallowed (private / loopback / link-local / metadata) address.

    Raised for any request to a URL the runtime did not choose: a webhook's
    callback URL, and the document, image or generated file a value points at,
    on the first request and on every redirect hop. It closes the DNS-rebinding
    gap that a request-time literal-IP check cannot: a URL like
    ``https://attacker.example/x`` passes a literal-host check, yet its DNS record
    can resolve to ``169.254.169.254`` / ``127.0.0.0/8`` / ``10.0.0.0/8`` by the
    time the request is made. The guard re-resolves at connect time and refuses
    the socket.

    A :class:`SecurityError` (not a ``WebhookDeliveryError`` or a
    ``RemoteFileFetchError``) on purpose: a blocked SSRF attempt is a security
    signal that must not be swallowed by the domain-level handlers around webhook
    delivery or a download's fallback — it surfaces and fails the delivery or the
    pipe.

    The guard cannot tell who supplied the URL, so the default is
    ``security.input_url_refused``: the destination was supplied from outside the
    runtime (a callback URL on the originating request, or a URL an input carried),
    and the caller fixes it by providing a public URL. A raise or catch site that
    knows the method named the URL chooses ``security.method_url_refused``, and one
    that knows a provider's answer named it ``security.provider_url_refused``.
    The message deliberately names only the requested hostname, never the
    resolved private IP, so it never reveals an internal address. That a name
    resolves to a private address at all stays observable, since the refusal is
    told apart from a host that cannot be reached.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.SECURITY_INPUT_URL_REFUSED,
        others=(CoreCode.SECURITY_METHOD_URL_REFUSED, CoreCode.SECURITY_PROVIDER_URL_REFUSED),
    )
