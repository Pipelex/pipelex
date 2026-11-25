from typing import ClassVar


class UsageStatsSwitchCases:
    TOOL_SWITCH_READINGS: ClassVar[list[tuple[str, bool]]] = [
        ("0", True),
        ("false", True),
        (" No ", True),
        ("OFF", True),
        ("", False),
        ("1", False),
        ("true", False),
        (" Yes", False),
        ("on", False),
        ("disabled", True),
        ("2", True),
    ]
    FLAG_READINGS: ClassVar[list[tuple[str, bool]]] = [
        ("", False),
        ("0", False),
        (" FALSE ", False),
        ("1", True),
        ("true", True),
        ("no", True),
        ("anything", True),
    ]
    ENDPOINT_OVERRIDES: ClassVar[list[tuple[str, bool]]] = [
        ("http://127.0.0.1:8123", True),
        ("http://localhost:9", True),
        ("http://[::1]:65535", True),
        ("http://127.0.0.1:0", False),
        ("http://127.0.0.1:65536", False),
        ("http://127.0.0.1:8123/batch/", False),
        ("http://127.0.0.1", False),
        ("https://127.0.0.1:8123", False),
        ("http://10.0.0.1:8123", False),
        ("https://eu.i.posthog.com", False),
        ("http://localhost.example.com:80", False),
        ("", False),
    ]
    PROJECT_SETTINGS: ClassVar[list[tuple[str | bytes, bool]]] = [
        ("[usage_stats]\nenabled = false\n", True),
        ("[usage_stats]\nenabled = true\n", False),
        ("[usage_stats]\n", False),
        ("[runtime]\nfoo = 1\n", False),
        ("", False),
        ("usage_stats = false\n", True),
        ('[usage_stats]\nenabled = "false"\n', True),
        ("[usage_stats]\nenabled = 0\n", True),
        ("[usage_stats\nenabled = false\n", True),
        (b"\xff\xfe[usage_stats]", True),
    ]


class UsageStatsCanary:
    """A string that must never appear in anything the statistics print, spool, send or store."""

    MARKER: ClassVar[str] = "zqcanary7x"
