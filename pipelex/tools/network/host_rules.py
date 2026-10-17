"""Host/IP classification rules for SSRF protection.

Single source of truth for the disallowed-destination CIDR set. Consumed both at
request-validation time (literal callback-URL host check) and at delivery time
(DNS re-resolution check in :mod:`pipelex.tools.network.ssrf_guard`). Keeping the
rule here means the API server and the worker classify the same address the same
way.
"""

from ipaddress import ip_address

from pipelex.errors.security_target import SecurityTargetClass

# The cloud metadata-server aliases: ``metadata`` / ``metadata.google.internal`` are GCP's.
_METADATA_HOSTNAMES: frozenset[str] = frozenset({"metadata.google.internal", "metadata"})

# The loopback alias.
_LOOPBACK_HOSTNAMES: frozenset[str] = frozenset({"localhost"})

# Hostnames that never resolve to a public destination but aren't literal IPs, so
# the IP-privateness check below can't catch them.
_DISALLOWED_HOSTNAMES: frozenset[str] = _METADATA_HOSTNAMES | _LOOPBACK_HOSTNAMES

# The cloud metadata endpoints by address: the link-local one AWS, GCP and Azure all serve, and AWS's IPv6 one.
_METADATA_IPS: frozenset[str] = frozenset({"169.254.169.254", "fd00:ec2::254"})


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


def classify_disallowed_host(host: str) -> SecurityTargetClass | None:
    """The class of destination a disallowed host is, for the security event its refusal emits.

    A cloud metadata endpoint, by alias or by address, is ``metadata``; ``localhost`` and a loopback address are
    ``loopback``; any other link-local address is ``link_local``; and every other address that is not publicly
    routable (private ranges, carrier-grade NAT, multicast, reserved, the unspecified address) is ``private``.
    The host is normalized as :func:`is_disallowed_host` normalizes it.

    Args:
        host: A host :func:`is_disallowed_host` refuses, a literal IP or a hostname.

    Returns:
        The host's class, or ``None`` for a host that is neither a known internal name nor a literal disallowed
        IP, an empty one among them, which the refusal names no class for.
    """
    normalized_host = host.rstrip(".").lower()
    if normalized_host in _METADATA_HOSTNAMES:
        return SecurityTargetClass.METADATA
    if normalized_host in _LOOPBACK_HOSTNAMES:
        return SecurityTargetClass.LOOPBACK
    if not is_disallowed_ip(normalized_host):
        return None
    addr = ip_address(normalized_host)
    if str(addr) in _METADATA_IPS:
        return SecurityTargetClass.METADATA
    if addr.is_loopback:
        return SecurityTargetClass.LOOPBACK
    if addr.is_link_local:
        return SecurityTargetClass.LINK_LOCAL
    return SecurityTargetClass.PRIVATE
