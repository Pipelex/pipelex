"""Secret scrubbing and injection-safe field values, in one processor that runs before any sink renders.

Two distinct removals, on two distinct parts of a record.

**Secrets are scrubbed** from the message and from every string a field carries. The pattern families
are the ones the workspace already wrote twice: the hosted plane's Lambdas ran them over their own
records, which is where the bearer tokens, the api-key and signature headers, the OAuth ``code``
parameter, the cookies, the JSON secret fields and the key prefixes come from. Running them here
instead means every Pipelex process gets them, whichever sink it selected, and a record a third-party
library emitted with a raw request in it is scrubbed too, because the processor sits on the sink's
handler rather than at the call sites.

**Control characters are neutralised** in a field's string values, and only there. A field value is
caller-supplied text, and a sink that writes a ``key=value`` run or a console line renders it as it is,
so a newline in it forges a line and a tab forges a separator; an escape byte forges colour on a
terminal. Each becomes its printable escape, the way ``pipelex-api`` escaped the values it flattened
into a log line. The **message** is left with its control characters, because they are the runtime's
own rendering and not a caller's string: a titled call and a structured content both put a newline
there deliberately, and escaping it would destroy every multi-line line the console draws.

A secret whose name and value are split across a mapping's key and its value is not caught: the
families read a name and a value out of one string, which is what a header line or a serialised JSON
blob gives them. A structured value is walked all the same, because a key prefix or a whole header
line sitting at any depth of it is caught by the families that need no context.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

from pipelex.tools.log.log_fields import carried_attributes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.tools.log.log_config import LogRedactionConfig
    from pipelex.tools.log.log_sink import LogRecordProcessor

# What a scrubbed secret is replaced by, everywhere: the line stays readable and says what was removed.
REDACTED_TEXT = "[REDACTED]"

# One compiled pattern and the text that replaces what it matched, a back-reference keeping whatever
# named the secret so a reader still sees which header or which field was carrying it.
RedactionPattern = tuple[re.Pattern[str], str]

# The shipped families, in the order they run. Ported from the hosted plane's own scrubber; a family
# is written to name the secret's carrier in the same string as the secret, which is what a header
# line, a query string or a serialised JSON object gives it.
SECRET_PATTERNS: tuple[RedactionPattern, ...] = (
    # An Authorization header carrying a bearer token.
    (re.compile(r"(?i)(authorization[\"'\s:=]+bearer\s+)([A-Za-z0-9._\-~+/=]{8,})"), rf"\1{REDACTED_TEXT}"),
    # An api-key header or entry, however it is spelled: x-api-key, api-key, api_key.
    (re.compile(r"(?i)([\"']?x?-?api[_-]key[\"']?\s*[:=]\s*[\"']?)([A-Za-z0-9._\-~+/=]{8,})"), rf"\1{REDACTED_TEXT}"),
    # A webhook signature header: x-signature, x-completion-signature.
    (re.compile(r"(?i)([\"']?x-(?:completion-)?signature[\"']?\s*[:=]\s*[\"']?)([A-Za-z0-9._\-~+/=]{8,})"), rf"\1{REDACTED_TEXT}"),
    # An OAuth authorization code in a query string.
    (re.compile(r"(?i)([?&]code=)([A-Za-z0-9._\-~+/=]{8,})"), rf"\1{REDACTED_TEXT}"),
    # A cookie header's whole value, whichever crumb it carries.
    (re.compile(r"(?i)((?:set-)?cookie[\"'\s:=]+)([^\"'\s,;][^\"',;]{4,})"), rf"\1{REDACTED_TEXT}"),
    # The JSON entries that are a secret whatever they hold, the OAuth code among them, since a
    # serialised event carries it as `"code": "..."`.
    (
        re.compile(
            r"([\"'](?:password|pipelex_api_key|gateway_api_key|jwt_secret_key|portkey_api_key|client_secret|code"
            r"|access_token|refresh_token|id_token)[\"']\s*:\s*[\"'])([^\"']+)([\"'])"
        ),
        rf"\1{REDACTED_TEXT}\3",
    ),
    # A key recognisable by its prefix alone, wherever it appears and whatever introduced it.
    (re.compile(r"\b((?:plx_sk_|sk_|pk_|bl_)[A-Za-z0-9_\-]{16,})\b"), REDACTED_TEXT),
)

# Every C0 and C1 control character, the DEL byte included. A newline or a tab forges a line or a field
# separator in a text sink, and an escape byte forges colour and cursor moves on a terminal.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# The escapes a reader recognises, for the three control characters that have a spelling of their own.
_NAMED_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

# The stdlib's own rendering of an exception, chain included, which is what ``Formatter.format`` would
# have put in ``exc_text`` had the processor not got there first.
_EXCEPTION_FORMATTER = logging.Formatter()


def _escaped_control_character(match: re.Match[str]) -> str:  # kw-only: ignore — ``re.sub`` calls its replacement positionally
    """The printable spelling of one control character: its named escape, or its hexadecimal one."""
    character = match.group()
    return _NAMED_ESCAPES.get(character) or f"\\x{ord(character):02x}"


def scrub_secrets(*, text: str, patterns: tuple[RedactionPattern, ...] = SECRET_PATTERNS) -> str:
    """Run every pattern over a string. Idempotent: a string already scrubbed comes back unchanged."""
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


def escape_control_characters(*, text: str) -> str:
    """The string with every control character replaced by its printable escape, and nothing else moved.

    Only the control characters move: accented text, CJK and emoji are left as they are, because the
    point is to stop a caller forging a line, not to reduce a value to ASCII.
    """
    return CONTROL_CHARACTERS.sub(_escaped_control_character, text)


def make_redaction_processor(*, config: LogRedactionConfig) -> LogRecordProcessor:
    """One processor for the sink seam, carrying the shipped families and whatever the configuration added.

    The patterns are compiled once, here, rather than on every record: a processor runs on the calling
    thread of every log call in the process.
    """
    patterns = SECRET_PATTERNS + tuple((re.compile(extra), REDACTED_TEXT) for extra in config.extra_patterns)

    def redact(record: logging.LogRecord) -> None:  # kw-only: ignore — the sink seam calls a processor positionally
        _redact_record(record=record, patterns=patterns)

    return redact


def _redact_record(*, record: logging.LogRecord, patterns: tuple[RedactionPattern, ...]) -> None:
    """Scrub the record's message and its exception text, and scrub and neutralise every string the record carries."""
    message = _rendered_message(record=record)
    if message is not None:
        scrubbed = scrub_secrets(text=message, patterns=patterns)
        if scrubbed != message:
            # The rendering replaces the format string and its arguments, because that is where the
            # secret was: a handler reading ``getMessage`` afterwards gets the scrubbed text, and one
            # reading ``msg`` gets it too rather than the template the arguments would fill back in.
            record.msg = scrubbed
            record.args = ()
    _redact_exception_text(record=record, patterns=patterns)
    for name, value in carried_attributes(record=record).items():
        setattr(record, name, _clean_value(value=value, patterns=patterns, open_containers=set()))


def _redact_exception_text(*, record: logging.LogRecord, patterns: tuple[RedactionPattern, ...]) -> None:
    """Render the exception the stdlib way, scrubbed, into ``exc_text``, where every formatter reads it first.

    ``Formatter.format`` renders ``exc_info`` into ``exc_text`` lazily and only when it is not already
    there, and the ``json`` sink reads it the same way, so a rendering put there before any sink runs
    is the one they all write. The exception object itself stays on the record, since a rendering can
    be scrubbed and an exception cannot; a sink that renders from the object rather than the text, the
    console's Rich traceback, is outside what this covers. A stack summary the call asked for rides
    ``stack_info`` as text already and is scrubbed in place.
    """
    if record.exc_text:
        record.exc_text = scrub_secrets(text=record.exc_text, patterns=patterns)
    elif record.exc_info:
        record.exc_text = scrub_secrets(text=_EXCEPTION_FORMATTER.formatException(record.exc_info), patterns=patterns)
    if record.stack_info:
        record.stack_info = scrub_secrets(text=record.stack_info, patterns=patterns)


def _rendered_message(*, record: logging.LogRecord) -> str | None:
    """The record's message as a handler would render it, or ``None`` when it cannot be rendered.

    ``getMessage`` interpolates the call's arguments, which is where a third-party library puts the
    value its format string names, so the secret is usually in the rendering rather than in ``msg``.
    A record whose arguments do not match its format string raises there; such a record is left exactly
    as it was, for the handler to fail on the way it always did, since redaction is not the place to
    turn one failure into another.
    """
    try:
        return record.getMessage()
    except Exception:  # ruff: ignore[blind-except]
        return None


def _clean_value(*, value: Any, patterns: tuple[RedactionPattern, ...], open_containers: set[int]) -> Any:
    """The value with every string it holds, at any depth, scrubbed of secrets and stripped of control characters.

    A mapping and a sequence are walked and rebuilt, a tuple coming back as a list the way a JSON
    rendering would have made it; everything else is returned as it was, a number, a boolean and a
    model included. A container that contains itself is returned as it is, as ``spell_non_finite``
    returns it, so the walk terminates and the sink meets the same value it always would have.
    """
    if isinstance(value, str):
        return escape_control_characters(text=scrub_secrets(text=value, patterns=patterns))
    container_id = id(value)
    if container_id in open_containers:
        return value
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        open_containers.add(container_id)
        try:
            return {key: _clean_value(value=item, patterns=patterns, open_containers=open_containers) for key, item in mapping.items()}
        finally:
            open_containers.discard(container_id)
    if isinstance(value, (list, tuple)):
        sequence = cast("Sequence[Any]", value)
        open_containers.add(container_id)
        try:
            return [_clean_value(value=item, patterns=patterns, open_containers=open_containers) for item in sequence]
        finally:
            open_containers.discard(container_id)
    return value
