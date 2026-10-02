"""Secret scrubbing and injection-safe field values, in one processor that runs before any sink renders.

Two distinct removals, on two distinct parts of a record.

**Secrets are scrubbed** from the message, from the exception's rendered text and from every string
a field carries. The pattern families are the ones the workspace already wrote twice: the hosted
plane's Lambdas ran them over their own records, which is where the bearer tokens, the api-key and
signature headers, the OAuth ``code`` parameter, the cookies, the JSON secret fields and the key
prefixes come from. Running them here instead means every Pipelex process gets them, whichever sink
it selected, and a record a third-party library emitted with a raw request in it is scrubbed too,
because the processor sits on the sink's handler rather than at the call sites. A structured value is
walked to any depth: a mapping entry named like a secret loses its value whatever it holds, since the
mapping split the name from the value the string families read together, and so does a field whose own
name is a secret's; a model is dumped and any other object rendered as text before the walk, exactly as
a wire sink would have done after it, and one that refuses to render loses that value alone. A
structured content is redacted by name before the dispatch renders it, so the message a sink writes
beside ``data`` is the rendering of what ``data`` holds rather than a second copy of the secret.

**Control characters are neutralised** in a field's string values, and only there. A field value is
caller-supplied text, and a sink that writes a ``key=value`` run or a console line renders it as it is,
so a newline in it forges a line and a tab forges a separator; an escape byte forges colour on a
terminal. Each becomes its printable escape, the way ``pipelex-api`` escaped the values it flattened
into a log line. The **message** and the **data** attribute keep their control characters, because
they are the runtime's own rendering and not a caller's string: a titled call and a structured content
both put a newline there deliberately, the wire sinks escape ``data`` themselves, and escaping it here
would turn a logged prompt's newlines into text no consumer can tell from a typed backslash.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, DATA_FIELD, UNSCRUBBED_MARK, carried_attributes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.tools.log.log_config import LogRedactionConfig
    from pipelex.tools.log.log_sink import LogRecordProcessor

# What a scrubbed secret is replaced by, everywhere: the line stays readable and says what was removed.
REDACTED_TEXT = "[REDACTED]"

# What a container that contains itself is cut at: the walk ends there, and the sink meets a marker
# rather than the raw container whose strings the scrub never reached.
CYCLE_TEXT = "[cycle]"

# What the message of a record whose scrub failed becomes, followed by the name of what was raised and
# a closing bracket: the sink writes a line that says the scrub failed, and nothing of the call.
QUARANTINE_PREFIX = "[REDACTION FAILED: "

# What a value that refuses to render becomes, followed by the name of what was raised and a closing
# bracket: that one value is lost, and the record and every other value it carries are handed on.
UNRENDERABLE_PREFIX = "[UNRENDERABLE: "

# What follows the format string of a record whose arguments do not fit it, in place of the arguments:
# the stdlib's own report of that failure prints them raw, which is exactly what the scrub removes.
ARGUMENTS_WITHHELD_TEXT = "[ARGUMENTS WITHHELD: the message could not be rendered]"

# The names under which a mapping entry is a secret whatever it holds, read lowercased and with a dash
# as an underscore, so a header name and a JSON key are both caught. ``code`` is not among them: it is
# the runtime's own identifier for a pipe, a domain and an error, and the OAuth code has its own family.
SECRET_KEY_NAMES = frozenset(
    {
        "password",
        "pipelex_api_key",
        "gateway_api_key",
        "jwt_secret_key",
        "portkey_api_key",
        "client_secret",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "api_key",
        "x_api_key",
        "x_signature",
        "x_completion_signature",
        "cookie",
        "set_cookie",
    }
)

# One compiled pattern and the text that replaces what it matched, a back-reference keeping whatever
# named the secret so a reader still sees which header or which field was carrying it.
RedactionPattern = tuple[re.Pattern[str], str]

# A quoted entry name whose value is a secret whatever it holds, and what introduces the value: the
# names a mapping key is read against, with a dash or an underscore wherever the name has an underscore
# and in any case, so a serialised object and a mapping key are judged by the same list.
_SECRET_ENTRY_NAMES = "|".join(sorted(re.escape(name).replace("_", "[-_]") for name in SECRET_KEY_NAMES))
_SECRET_ENTRY_KEY = rf"[\"'](?:{_SECRET_ENTRY_NAMES})[\"']\s*:\s*"

# What a secret's value looks like once something has named it: the characters a token, a key, a hash or
# a percent-encoded parameter is written in, and at least eight of them. The bound is what keeps these
# families off ordinary prose, where a name followed by a colon is a sentence rather than a header; a
# secret shorter than it is below what the shipped families read at all, in this repo as in the hosted
# plane's scrubber they were ported from.
_SECRET_VALUE = r"[A-Za-z0-9._\-~+/=%]{8,}"

# A cookie header's value, in the grammar RFC 6265 gives it rather than as a run to the end of the line.
# The first crumb must be ``name=value``, which is what tells a header from prose that merely says
# "cookie:" before a sentence; the value is either double-quoted, or a run holding no quote, no comma
# and no semicolon, which is exactly what the RFC admits, so a value holding an apostrophe is read whole
# and one holding a double quote is read to its closing quote. The crumbs and flag attributes after the
# first are taken with it, so the whole header goes and not only its first cookie.
_COOKIE_VALUE = r"(?:\"[^\"\r\n]*\"|[^\s;,\"\r\n]*)"
_COOKIE_RUN = rf"[^\s;=,\"\r\n]+={_COOKIE_VALUE}(?:\s*;\s*[^\s;=,\"\r\n]+(?:={_COOKIE_VALUE})?)*"

# The shipped families, in the order they run. Ported from the hosted plane's own scrubber; a family
# is written to name the secret's carrier in the same string as the secret, which is what a header
# line, a query string or a serialised JSON object gives it.
SECRET_PATTERNS: tuple[RedactionPattern, ...] = (
    # An Authorization header, whichever scheme it carries. The schemes are named rather than read as
    # "whatever word follows", because the header name introduces its value with whitespace as readily
    # as with a colon, and a pattern taking any word there redacts the next word of a sentence that
    # merely says "authorization". The scheme is kept, being what tells a reader which credential went.
    (re.compile(rf"(?i)(authorization[\"'\s:=]+(?:bearer|basic|token|digest|negotiate|hmac)\s+)({_SECRET_VALUE})"), rf"\1{REDACTED_TEXT}"),
    # An api-key header or entry, however it is spelled: x-api-key, api-key, api_key.
    (re.compile(rf"(?i)([\"']?x?-?api[_-]key[\"']?\s*[:=]\s*[\"']?)({_SECRET_VALUE})"), rf"\1{REDACTED_TEXT}"),
    # A webhook signature header: x-signature, x-completion-signature.
    (re.compile(rf"(?i)([\"']?x-(?:completion-)?signature[\"']?\s*[:=]\s*[\"']?)({_SECRET_VALUE})"), rf"\1{REDACTED_TEXT}"),
    # An OAuth authorization code in a query string, read to the delimiter that ends the parameter
    # rather than through an alphabet of its own: a code is routinely percent-encoded, and a class that
    # stops at the escape leaves the tail behind — or the whole code, when the escape falls early enough
    # that what precedes it is shorter than the minimum length.
    (re.compile(r"(?i)([?&]code=)([^&#\s\"'\r\n]{8,})"), rf"\1{REDACTED_TEXT}"),
    # The serialised entries that are a secret whatever they hold, a JSON object and a Python ``repr``
    # alike. A quoted value is read up to the same quote that opened it, whichever quoted the name, with
    # a backslash escape honoured, so a value holding the other quote character or an escaped one is
    # removed whole; a number or a boolean is removed as the bare token it is. A nested object or list
    # is beyond a pattern, which is why a structured content is redacted by name before it is rendered.
    # ``code`` is not among the names: it is the runtime's own identifier for a pipe, a domain and an
    # error, and the OAuth code has the query-string family above. These run before the raw-header
    # families below, so a header serialised as an entry is removed as an entry, quotes and all, and a
    # raw-header family never reads into the JSON punctuation around it.
    (re.compile(rf'(?i)({_SECRET_ENTRY_KEY}")((?:\\.|[^"\\])+)(")'), rf"\1{REDACTED_TEXT}\3"),
    (re.compile(rf"(?i)({_SECRET_ENTRY_KEY}')((?:\\.|[^'\\])+)(')"), rf"\1{REDACTED_TEXT}\3"),
    (re.compile(rf"(?i)({_SECRET_ENTRY_KEY})(-?\d[\w.+-]*|true|false)(?![\w.+-])"), rf"\1{REDACTED_TEXT}"),
    # A raw cookie header's whole value, every crumb and every flag attribute of it. The value has to be
    # a cookie header's own ``name=value`` grammar, which is what separates a header from prose: a
    # sentence that merely says "cookie:" or "cookie=" before ordinary words is left alone, where a run
    # to the end of the line destroyed the rest of it — the secret a later word carried among it.
    (re.compile(rf"(?i)\b((?:set-)?cookie[\"']?\s*[:=]\s*[\"']?)({_COOKIE_RUN})"), rf"\1{REDACTED_TEXT}"),
    # The same secret names again, named in the plain ``name=value`` or ``name: value`` form a query
    # string, a form-encoded body or a header line writes them in. The entry families above read them
    # only when something quoted the name, which is the serialised shape and not the shape a raw request
    # reaches this processor in. The colon or the equals sign is required and the value must be at least
    # eight characters of what a secret is written in, which is what keeps this off ordinary prose.
    (re.compile(rf"(?i)((?:{_SECRET_ENTRY_NAMES})\s*[:=]\s*)({_SECRET_VALUE})"), rf"\1{REDACTED_TEXT}"),
    # A key recognisable by its prefix alone, wherever it appears and whatever introduced it. The
    # prefix is spelled with a dash as with an underscore, since that is how the keys in use are
    # actually issued, and what follows it has to end in a long unbroken run of letters and digits: an
    # ordinary snake_case identifier — a table, a column, a partition — is words all the way down, and
    # a family reading the prefix alone redacted those. The prefix is kept, as every other family keeps
    # what named the secret, so a reader still sees which kind of key was carried.
    (re.compile(r"\b((?:plx[_-]sk|sk|pk|bl)[_-])((?:[A-Za-z0-9]{1,8}[_-]){0,2}[A-Za-z0-9]{16,})(?![A-Za-z0-9])"), rf"\1{REDACTED_TEXT}"),
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
        try:
            _redact_record(record=record, patterns=patterns)
        except Exception as exc:
            # Fails closed, in two steps that do not depend on each other. The mark goes on first, by
            # assignment into the record's own dictionary, which needs no call and no frame: whatever
            # happens next, the guard on the sink's handler has been told not to hand this record on.
            # Then the strip, which turns the record into a notice and lifts the mark when it gets all
            # the way through. It is the strip that can fail a second time — the failure that brings us
            # here is routinely a stack that has run out, and a stack that cannot take ``_redact_record``
            # cannot always take the stripping of what it left behind either.
            record.__dict__[UNSCRUBBED_MARK] = True
            _quarantine(record=record, exc=exc)
            raise

    return redact


def _quarantine(*, record: logging.LogRecord, exc: Exception) -> None:
    """Strip a record whose scrub failed down to a notice naming the failure, so nothing unscrubbed leaves with it.

    The mark ``redact`` set is lifted at the end and only there, so a strip that gets partway leaves the
    record marked and the record is dropped rather than emitted as a notice that says it was stripped
    while still carrying what the scrub never read.
    """
    record.msg = f"{QUARANTINE_PREFIX}{type(exc).__name__}]"
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    for name in carried_attributes(record=record):
        setattr(record, name, REDACTED_TEXT)
    record.__dict__.pop(UNSCRUBBED_MARK, None)


def _redact_record(*, record: logging.LogRecord, patterns: tuple[RedactionPattern, ...]) -> None:
    """Scrub the record's message and its exception text, and scrub and neutralise every string the record carries."""
    message = _rendered_message(record=record)
    if message is None:
        _withhold_arguments(record=record, patterns=patterns)
    else:
        scrubbed = scrub_secrets(text=message, patterns=patterns)
        if scrubbed != message:
            # The rendering replaces the format string and its arguments, because that is where the
            # secret was: a handler reading ``getMessage`` afterwards gets the scrubbed text, and one
            # reading ``msg`` gets it too rather than the template the arguments would fill back in.
            record.msg = scrubbed
            record.args = ()
    _redact_exception_text(record=record, patterns=patterns)
    for name, value in carried_attributes(record=record).items():
        # A field whose own name is a secret's loses its value whatever it holds, exactly as a mapping
        # entry does. ``data`` keeps its control characters for the reason the message does: it is the
        # runtime's own rendering of the caller's object, and the wire sinks escape it themselves.
        setattr(
            record,
            name,
            REDACTED_TEXT
            if _is_secret_field_name(name=name)
            else _clean_value(value=value, patterns=patterns, open_containers=set(), is_escaping_control_characters=name != DATA_FIELD),
        )


def _is_secret_field_name(*, name: str) -> bool:
    """Whether the name a field is carried under is a secret's, read with every collision prefix taken off first.

    A field lands under a prefixed name whenever the record already owns the name the caller used, and a
    record factory that stamps ``password`` is enough to do it — so the name reaching a sink is
    ``field_password`` while the value under it is exactly the one the caller asked to have redacted.
    Judging the name as it was spelled rather than as it was carried covers that, and covers a caller who
    spelled the prefix themselves, which is the safe direction to be wrong in.
    """
    while name.startswith(COLLIDING_FIELD_PREFIX):
        name = name[len(COLLIDING_FIELD_PREFIX) :]
    return _is_secret_key(key=name)


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
    A record whose arguments do not match its format string raises there, and ``_withhold_arguments``
    decides what it becomes.
    """
    try:
        return record.getMessage()
    except Exception:  # ruff: ignore[blind-except]
        return None


def _withhold_arguments(*, record: logging.LogRecord, patterns: tuple[RedactionPattern, ...]) -> None:
    """Replace the arguments of a record whose message cannot be rendered by a notice, after its scrubbed format string.

    Left as it was, the record would fail again in the handler, and the stdlib's report of that failure
    prints the format string and every argument to stderr as they are, the value a secret pattern would
    have removed among them. With no arguments the stdlib renders the format string as it stands, so the
    line still says which call it was; a format string that cannot even be read as text is dropped too.
    """
    try:
        template = scrub_secrets(text=str(record.msg), patterns=patterns)
    except Exception:  # ruff: ignore[blind-except]
        record.msg = ARGUMENTS_WITHHELD_TEXT
    else:
        record.msg = f"{template} {ARGUMENTS_WITHHELD_TEXT}"
    record.args = ()


def redact_secret_entries(*, value: Any, open_containers: set[int] | None = None) -> Any:
    """A JSON-ready value with every mapping entry named like a secret replaced by the redaction text, at any depth.

    For a structured content, before the dispatch renders it: the message it writes is that rendering,
    and a secret nested in an object or held as a number is beyond what the string families can read
    back out of text. What comes back is a new value wherever an entry was replaced, and the value
    itself otherwise.

    A container that contains itself is cut at the cycle, exactly as the field walk cuts one. The walk
    has to survive a cycle because the caller that needs it most is the one rendering content ``json``
    has just refused, and a circular reference is the commonest reason it refuses.
    """
    if open_containers is None:
        open_containers = set()
    container_id = id(value)
    if isinstance(value, Mapping):
        if container_id in open_containers:
            return CYCLE_TEXT
        mapping = cast("Mapping[Any, Any]", value)
        open_containers.add(container_id)
        try:
            return {
                key: REDACTED_TEXT if _is_secret_key(key=key) else redact_secret_entries(value=item, open_containers=open_containers)
                for key, item in mapping.items()
            }
        finally:
            open_containers.discard(container_id)
    if isinstance(value, (list, tuple)):
        if container_id in open_containers:
            return CYCLE_TEXT
        sequence = cast("Sequence[Any]", value)
        open_containers.add(container_id)
        try:
            items = [redact_secret_entries(value=item, open_containers=open_containers) for item in sequence]
        finally:
            open_containers.discard(container_id)
        if isinstance(value, list):
            return items
        # A tuple is walked as the field walk walks one, since the ``repr`` fallback writes whatever it
        # holds. It keeps its shape there, and it is handed back as it was when nothing in it changed,
        # so a named tuple that carried no secret keeps its name in the rendering.
        if all(new is old for new, old in zip(items, sequence, strict=True)):
            return sequence
        return tuple(items)
    return value


def _is_secret_key(*, key: Any) -> bool:
    """Whether a mapping key names a secret, read lowercased and with a dash as an underscore."""
    return isinstance(key, str) and key.lower().replace("-", "_") in SECRET_KEY_NAMES


def _clean_value(*, value: Any, patterns: tuple[RedactionPattern, ...], open_containers: set[int], is_escaping_control_characters: bool) -> Any:
    """The value with every string it holds, at any depth, scrubbed of secrets, and its control characters escaped when asked.

    A mapping and a sequence are walked and rebuilt, a tuple coming back as a list the way a JSON
    rendering would have made it, and a mapping entry named like a secret loses its value whatever
    the value is, since the mapping split the name from the value the string families read together.
    A model is dumped and an object is rendered as text before the walk, exactly as the wire sinks
    would have dumped and rendered them after it, so neither carries a secret past the scrub. A
    number, a boolean and ``None`` come back as they are. A container that contains itself is cut at
    the cycle with a marker: kept raw, it would hand its unscrubbed strings to a sink's fallback rendering.
    A model whose dump raises and an object whose text raises become a marker naming what was raised,
    and nothing of what it said, which may be the very value it failed on: one value that refuses to
    render costs that value, not the record and every other value beside it.
    """
    if isinstance(value, str):
        scrubbed = scrub_secrets(text=value, patterns=patterns)
        return escape_control_characters(text=scrubbed) if is_escaping_control_characters else scrubbed
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, BaseModel):
        try:
            value = value.model_dump(mode="json")
        except Exception as exc:  # ruff: ignore[blind-except]
            return _unrenderable_text(exc=exc)
    container_id = id(value)
    if container_id in open_containers:
        return CYCLE_TEXT
    if isinstance(value, Mapping):
        mapping = cast("Mapping[Any, Any]", value)
        open_containers.add(container_id)
        try:
            return {
                key: REDACTED_TEXT
                if _is_secret_key(key=key)
                else _clean_value(
                    value=item, patterns=patterns, open_containers=open_containers, is_escaping_control_characters=is_escaping_control_characters
                )
                for key, item in mapping.items()
            }
        finally:
            open_containers.discard(container_id)
    if isinstance(value, (list, tuple)):
        sequence = cast("Sequence[Any]", value)
        open_containers.add(container_id)
        try:
            return [
                _clean_value(
                    value=item, patterns=patterns, open_containers=open_containers, is_escaping_control_characters=is_escaping_control_characters
                )
                for item in sequence
            ]
        finally:
            open_containers.discard(container_id)
    # What ``json_fallback`` would have written for it, scrubbed before it is written.
    try:
        text = str(value)
    except Exception as exc:  # ruff: ignore[blind-except]
        return _unrenderable_text(exc=exc)
    return _clean_value(value=text, patterns=patterns, open_containers=open_containers, is_escaping_control_characters=is_escaping_control_characters)


def _unrenderable_text(*, exc: Exception) -> str:
    """The marker a value that refused to render is carried as: the name of what it raised, and nothing of its text."""
    return f"{UNRENDERABLE_PREFIX}{type(exc).__name__}]"
