from pipelex.base_exceptions import ErrorDomain, SecurityError


class SsrfBlockedError(SecurityError):
    """Raised when an outbound request is refused because the destination host
    resolved to a disallowed (private / loopback / link-local / metadata) address.

    Closes the DNS-rebinding gap that a request-time literal-IP check cannot:
    a callback URL like ``https://attacker.example/cb`` passes a literal-host
    check, yet its DNS record can resolve to ``169.254.169.254`` / ``127.0.0.0/8``
    / ``10.0.0.0/8`` by the time the worker actually fires the webhook. The guard
    re-resolves at connect time and refuses the socket.

    A :class:`SecurityError` (not a ``WebhookDeliveryError``) on purpose: a
    blocked SSRF attempt is a security signal that must not be swallowed by the
    domain-level ``except httpx.RequestError`` handlers around webhook delivery —
    it surfaces and aborts the delivery.

    ``error_domain = INPUT`` because the destination was caller-supplied (a
    callback URL on the originating request); the caller fixes it by providing a
    public URL. ``_authors_caller_facing_message`` lets the message survive STRICT
    disclosure — it deliberately names only the caller's own hostname, never the
    resolved private IP, so it cannot confirm internal network topology to a
    probing client.
    """

    error_domain = ErrorDomain.INPUT
    _declared_title = "Outbound request blocked (SSRF guard)"
    _authors_caller_facing_message = True
