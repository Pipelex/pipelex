import pytest

from pipelex.tools.network.host_rules import is_disallowed_host, is_disallowed_ip


class TestHostRules:
    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("127.0.0.1", True),  # loopback
            ("169.254.169.254", True),  # link-local: cloud metadata endpoint
            ("10.0.0.5", True),  # private RFC 1918
            ("192.168.1.1", True),  # private RFC 1918
            ("172.16.0.1", True),  # private RFC 1918
            ("100.64.0.1", True),  # carrier-grade NAT (RFC 6598) — not globally routable
            ("192.0.2.1", True),  # TEST-NET-1 documentation range
            ("198.18.0.1", True),  # benchmarking range
            ("224.0.0.1", True),  # multicast (is_global=True, caught explicitly)
            ("64:ff9b::1.2.3.4", True),  # NAT64 well-known prefix (is_global=True, is_reserved)
            ("0.0.0.0", True),  # noqa: S104 # unspecified address — asserting it is disallowed
            ("::1", True),  # IPv6 loopback
            ("fe80::1", True),  # IPv6 link-local
            ("8.8.8.8", False),  # public
            ("1.1.1.1", False),  # public
            ("93.184.216.34", False),  # public (example.com)
            ("2606:2800:220:1:248:1893:25c8:1946", False),  # public IPv6
            ("not-an-ip", False),  # a hostname is not a literal IP
        ],
    )
    def test_is_disallowed_ip(self, host: str, expected: bool) -> None:
        assert is_disallowed_ip(host) is expected

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("", True),  # empty host
            ("localhost", True),
            ("metadata", True),  # GCP metadata alias
            ("metadata.google.internal", True),  # GCP metadata server
            ("LOCALHOST", True),  # case-insensitive: uppercase must still match
            ("LocalHost", True),  # case-insensitive: mixed case must still match
            ("METADATA", True),  # case-insensitive alias
            ("metadata.google.internal.", True),  # absolute FQDN (trailing dot) is equivalent
            ("localhost.", True),  # absolute FQDN form of loopback alias
            (".", True),  # dots-only normalizes to empty → disallowed
            ("127.0.0.1", True),  # literal loopback
            ("127.0.0.1.", True),  # trailing-dot literal IP normalizes and is still caught
            ("169.254.169.254", True),  # literal metadata IP
            ("10.0.0.5", True),  # literal private IP
            ("100.64.0.1", True),  # literal carrier-grade NAT IP
            ("example.com", False),  # ordinary public hostname
            ("example.com.", False),  # absolute FQDN of a public host stays allowed
            ("api.openai.com", False),
            ("8.8.8.8", False),  # literal public IP
        ],
    )
    def test_is_disallowed_host(self, host: str, expected: bool) -> None:
        assert is_disallowed_host(host) is expected
