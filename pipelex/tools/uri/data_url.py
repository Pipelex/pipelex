"""The one reading of a `data:` URL: its header's media type, whether it is base64, and its payload.

The header is read as RFC 2397 and the WHATWG "data: URL processor" read it, so no reader here disagrees with a browser
about where it ends: the scheme `data:` is matched without regard to ASCII case, the header is everything before the
first comma, stripped of leading and trailing ASCII whitespace, and the URL is base64 when the header ends with
`;base64`, matched without regard to ASCII case and with optional spaces after the `;`. The payload is everything after
that first comma, as written: it is neither percent-decoded nor base64-decoded here.

Every reading of a data URL in the runtime goes through `parse_data_url`: `resolve_uri`, the base64 helpers of
`pipelex.tools.misc.base64_utils` and the header strip of `detect_file_type_from_base64`.
"""

import re
from typing import Final, NamedTuple

from pipelex.tools.uri.data_url_exceptions import DataUrlError

DATA_URL_SCHEME: Final[str] = "data:"

# The form of a data URL every reader of bytes accepts, named in the errors that refuse another.
ACCEPTED_DATA_URL_FORM: Final[str] = "data:<type>/<subtype>[;parameters];base64,<payload>"

# The ASCII whitespace the WHATWG URL standard strips: tab, line feed, form feed, carriage return and space.
_ASCII_WHITESPACE: Final[str] = "\t\n\f\r "

# A header ending with `;`, optional spaces, then `base64`. ASCII-only, so no Unicode case folding stretches `base64`.
_BASE64_HEADER_SUFFIX: Final[re.Pattern[str]] = re.compile(r";\x20*base64\Z", re.IGNORECASE | re.ASCII)


class ParsedDataUrl(NamedTuple):
    """A `data:` URL read into its parts.

    Attributes:
        media_type: The header's media type as written, parameters included and the `;base64` marker removed, stripped of
            ASCII whitespace; an empty string when the header declares none, which includes a header that gives
            parameters without a type, such as `data:;charset=utf-8;base64,`, which RFC 2397 allows.
        is_base64: Whether the header ends with the `;base64` marker.
        payload: Everything after the header's comma, as written.
    """

    media_type: str
    is_base64: bool
    payload: str


def is_data_url(*, uri: str) -> bool:
    """Whether `uri` starts with the `data:` scheme, in any ASCII case."""
    scheme = uri[: len(DATA_URL_SCHEME)]
    return scheme.isascii() and scheme.lower() == DATA_URL_SCHEME


def parse_data_url(*, uri: str) -> ParsedDataUrl:
    """Read a `data:` URL into its header's media type, whether it is base64, and its payload.

    Args:
        uri: The `data:` URL.

    Returns:
        The URL's parts: `data:text/plain;charset=utf-8;base64,aGVsbG8=` reads as the media type
        `text/plain;charset=utf-8`, base64, and the payload `aGVsbG8=`.

    Raises:
        DataUrlError: `uri` does not start with `data:`, or holds no comma ending its header.
    """
    if not is_data_url(uri=uri):
        msg = "The value is not a data URL: it does not start with 'data:'"
        raise DataUrlError(msg)
    header, comma, payload = uri[len(DATA_URL_SCHEME) :].partition(",")
    if not comma:
        msg = f"The data URL holds no comma ending its header. The form read is {ACCEPTED_DATA_URL_FORM}"
        raise DataUrlError(msg)
    media_type = header.strip(_ASCII_WHITESPACE)
    base64_marker = _BASE64_HEADER_SUFFIX.search(media_type)
    if base64_marker is None:
        return ParsedDataUrl(media_type=_declared_type(header_type=media_type), is_base64=False, payload=payload)
    return ParsedDataUrl(media_type=_declared_type(header_type=media_type[: base64_marker.start()]), is_base64=True, payload=payload)


def _declared_type(*, header_type: str) -> str:
    """The header's type stripped of ASCII whitespace, or an empty string when nothing stands before its first `;`.

    RFC 2397 lets a header give parameters without a type (`data:;charset=utf-8,`), which declares no type, as a header
    with nothing at all does.
    """
    stripped = header_type.strip(_ASCII_WHITESPACE)
    if not stripped.split(";", 1)[0].strip(_ASCII_WHITESPACE):
        return ""
    return stripped


def parse_base64_data_url(*, uri: str) -> ParsedDataUrl:
    """Read a `data:` URL that must be base64, as every reader of its bytes needs it to be.

    Raises:
        DataUrlError: `uri` is not a `data:` URL, holds no comma ending its header, or is not base64.
    """
    parsed = parse_data_url(uri=uri)
    if not parsed.is_base64:
        msg = f"The data URL is not base64. The form read is {ACCEPTED_DATA_URL_FORM}"
        raise DataUrlError(msg)
    return parsed
