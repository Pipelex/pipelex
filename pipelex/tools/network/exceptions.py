from pipelex.base_exceptions import ErrorDomain, SecurityError


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

    ``error_domain = INPUT`` because the destination was supplied from outside the
    runtime (a callback URL on the originating request, or a URL a method's value
    carried); the caller fixes it by providing a public URL.
    ``_authors_caller_facing_message`` lets the message survive STRICT
    disclosure — it deliberately names only the requested hostname, never the
    resolved private IP, so it never reveals an internal address to a probing
    client. That a name resolves to a private address at all stays observable,
    since the refusal is told apart from a host that cannot be reached.
    """

    error_domain = ErrorDomain.INPUT
    _declared_title = "Outbound request blocked (SSRF guard)"
    _authors_caller_facing_message = True
