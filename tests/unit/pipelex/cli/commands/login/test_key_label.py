"""`pipelex login --label` trims a label as the app does, refuses one it cannot send, and passes it to `/auth/cli`."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from pipelex.cli.commands.login.command import KEY_LABEL_MAX_LENGTH, build_cli_auth_url, key_label_refusal, quote_for_shell, trim_key_label

APP_URL = "https://app.test"
STATE = "a-state_value.0~"
#: The refusal sentences the workshop's `pipelex login` (`@pipelex/mcp`) prints too.
EMPTY = "The key label is empty once trimmed: a label is 1 to 64 characters."
TOO_LONG = "The key label is longer than 64 characters: a label is 1 to 64 characters."
CONTROL_CHARACTER = "The key label holds a control character, such as a tab or a line break, which a key label cannot hold."
KEY_PREFIX = "The key label starts with plx_sk_, as a Pipelex API key does: give --label a name for the key, never the key itself."
NOT_TEXT = "The key label holds bytes that are not text, so it cannot be sent to the Pipelex app."


class TestKeyLabel:
    def test_a_url_without_a_label_carries_the_port_and_the_state_only(self) -> None:
        url = build_cli_auth_url(app_origin=APP_URL, callback_port=53682, state=STATE)

        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == f"{APP_URL}/auth/cli"
        assert parse_qs(parts.query) == {"callback_port": ["53682"], "state": [STATE]}

    @pytest.mark.parametrize("label", ["qa.dev.lab.builder", "Lab & co #1", "nightly import", "a+b=c?d/e", "Lab é ✓ \U0001f511"])
    def test_a_url_with_a_label_carries_it_encoded(self, label: str) -> None:
        url = build_cli_auth_url(app_origin=APP_URL, callback_port=53682, state=STATE, label=label)

        query = parse_qs(urlsplit(url).query)
        assert query == {"callback_port": ["53682"], "state": [STATE], "label": [label]}

    @pytest.mark.parametrize(
        ("raw", "trimmed"),
        [
            ("  qa.dev.lab.builder  ", "qa.dev.lab.builder"),
            ("\tnightly import\r\n", "nightly import"),
            ("\u00a0\ufeffLab\u3000\u2028", "Lab"),
            # JavaScript's trim keeps these, so the app reads them as part of the label, and so does this login.
            ("\x1cLab\x85", "\x1cLab\x85"),
            ("\u200bLab", "\u200bLab"),
        ],
    )
    def test_a_label_is_trimmed_as_javascript_trims_it(self, raw: str, trimmed: str) -> None:
        assert trim_key_label(label=raw) == trimmed

    @pytest.mark.parametrize(
        "label",
        [
            "x",
            "x" * KEY_LABEL_MAX_LENGTH,
            f"Lab é {'x' * (KEY_LABEL_MAX_LENGTH - 6)}",
            # Counted in code points, as the app and the platform count them, so an emoji is one character.
            "\U0001f511" * KEY_LABEL_MAX_LENGTH,
            "plx_sk",
            "my plx_sk_ notes",
        ],
    )
    def test_a_label_the_app_takes_is_not_refused(self, label: str) -> None:
        assert key_label_refusal(label=trim_key_label(label=label)) is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("", EMPTY),
            ("   ", EMPTY),
            ("\u00a0\ufeff\u2028", EMPTY),
            ("x" * (KEY_LABEL_MAX_LENGTH + 1), TOO_LONG),
            ("\U0001f511" * (KEY_LABEL_MAX_LENGTH + 1), TOO_LONG),
            ("a\tb", CONTROL_CHARACTER),
            ("line\nbreak", CONTROL_CHARACTER),
            # The platform strips U+0085 where the app keeps it, so the stored label would differ from the one named.
            ("ci\x85", CONTROL_CHARACTER),
            ("\x1fci", CONTROL_CHARACTER),
            ("lab\x1b[31m", CONTROL_CHARACTER),
            ("plx_sk_0123abcdef", KEY_PREFIX),
            ("  plx_sk_0123abcdef  ", KEY_PREFIX),
            # What a shell hands over from bytes that are not UTF-8 text.
            ("lab\udcff", NOT_TEXT),
        ],
    )
    def test_a_label_that_cannot_be_sent_is_refused_saying_why(self, raw: str, expected: str) -> None:
        assert key_label_refusal(label=trim_key_label(label=raw)) == expected

    @pytest.mark.parametrize(
        ("label", "posix", "windows"),
        [
            ("qa.dev.lab.builder", "qa.dev.lab.builder", '"qa.dev.lab.builder"'),
            ("my laptop", "'my laptop'", '"my laptop"'),
            ("Lab & whoami", "'Lab & whoami'", '"Lab & whoami"'),
            ("it's a <lab> | ^", "'it'\"'\"'s a <lab> | ^'", '"it\'s a <lab> | ^"'),
            # cmd.exe expands `%` and PowerShell `$` and the backtick inside double quotes, and neither holds a `"`.
            ("100%", "100%", None),
            ("$HOME lab", "'$HOME lab'", None),
            ("lab`n", "'lab`n'", None),
            ('say "hi"', "'say \"hi\"'", None),
        ],
    )
    def test_the_retry_label_is_quoted_for_the_shell_it_is_copied_into(self, label: str, posix: str, windows: str | None) -> None:
        assert quote_for_shell(value=label, windows=False) == posix
        assert quote_for_shell(value=label, windows=True) == windows
