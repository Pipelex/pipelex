"""Host/IP classification rules for SSRF protection.

Single source of truth for the disallowed-destination CIDR set. Consumed both at
request-validation time (literal callback-URL host check) and at delivery time
(DNS re-resolution check in :mod:`pipelex.tools.network.ssrf_guard`). Keeping the
rule here means the API server and the worker classify the same address the same
way.
"""

from ipaddress import ip_address

# Hostnames that never resolve to a public destination but aren't literal IPs, so
# the IP-privateness check below can't catch them. ``metadata`` /
# ``metadata.google.internal`` are the GCP metadata-server aliases; ``localhost``
# is the loopback alias.
_DISALLOWED_HOSTNAMES: frozenset[str] = frozenset({"localhost", "metadata.google.internal", "metadata"})


def is_disallowed_ip(host: str) -> bool:
    """True when ``host`` is a literal IP an outbound request must refuse.

    Deny-by-default: anything **not globally routable** is refused. ``is_global``
    is ``False`` for private (RFC 1918), loopback (127/8, ::1), link-local
    (169.254/16 — incl. the 169.254.169.254 cloud-metadata endpoint), carrier-grade
    NAT (100.64/10, RFC 6598), shared / documentation / benchmarking ranges, and
    the unspecified address — so a range we forgot to enumerate cannot leak
    through. ``is_multicast`` and ``is_reserved`` are checked explicitly because
    ``ipaddress`` classifies some of those as ``is_global`` (the 224.0.0.0/4
    multicast block, the 64:ff9b::/96 NAT64 prefix), and they are not valid
    outbound destinations either.

    Returns ``False`` for any string that is not a literal IP address — a
    hostname is classified by :func:`is_disallowed_host` (literal-name set) and,
    at delivery time, by resolving it and re-checking each resolved IP here.
    """
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    return not addr.is_global or addr.is_multicast or addr.is_reserved


def is_disallowed_host(host: str) -> bool:
    """True when ``host`` is a destination an outbound request must refuse.

    Cheap, resolution-free check: an empty host, a known internal hostname
    (``localhost`` / cloud metadata aliases), or a literal IP in a private range.
    A normal public hostname returns ``False`` here — it can still resolve to a
    private IP at fire time, which is why the delivery-time guard
    (:mod:`pipelex.tools.network.ssrf_guard`) re-resolves and re-checks. This
    function is the request-time first line of defense and the literal-host arm
    of the delivery-time guard.

    The host is normalized first: hostnames are case-insensitive and an absolute
    (trailing-dot) FQDN is equivalent to its dotless form, so ``LOCALHOST`` and
    ``metadata.google.internal.`` must classify the same as their canonical
    forms — otherwise these common variants would slip past the blocklist.
    """
    if not host:
        return True
    normalized_host = host.rstrip(".").lower()
    if not normalized_host:
        return True
    if normalized_host in _DISALLOWED_HOSTNAMES:
        return True
    return is_disallowed_ip(normalized_host)
