"""HTTP codec server for the Temporal Web UI.

Exposes ``POST /encode`` and ``POST /decode`` endpoints that the Temporal Web UI
can call to transparently decode payloads offloaded by :class:`StoragePayloadCodec`.
Without this server, the UI shows opaque ``binary/storage-ref`` blobs instead of
the actual workflow data.

Usage::

    python -m pipelex.temporal.codec.codec_server_cli
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Awaitable, Callable

from aiohttp import hdrs, web
from google.protobuf import json_format
from temporalio.api.common.v1 import Payload, Payloads

from pipelex import log
from pipelex.tools.storage.exceptions import StorageFileNotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.temporal.codec.storage_payload_codec import StoragePayloadCodec


def _set_cors_headers(response: web.Response, request_origin: str, cors_origins: list[str]) -> None:
    """Set CORS headers on the response if the request origin is allowed."""
    if request_origin in cors_origins:
        response.headers[hdrs.ACCESS_CONTROL_ALLOW_ORIGIN] = request_origin
        response.headers[hdrs.ACCESS_CONTROL_ALLOW_METHODS] = "POST"
        response.headers[hdrs.ACCESS_CONTROL_ALLOW_HEADERS] = "content-type,x-namespace"


def _make_cors_handler(cors_origins: list[str]) -> Callable[[web.Request], Awaitable[web.Response]]:
    """Create a CORS preflight handler for the given origins."""

    async def cors_options(request: web.Request) -> web.Response:  # noqa: RUF029 — must be async for aiohttp
        response = web.Response()
        _set_cors_headers(response, request.headers.get(hdrs.ORIGIN, ""), cors_origins)
        return response

    return cors_options


def _error_response(request: web.Request, cors_origins: list[str], status: int, text: str) -> web.Response:
    """Build an error response with CORS headers so browsers see the diagnostic message."""
    response = web.Response(status=status, text=text)
    _set_cors_headers(response, request.headers.get(hdrs.ORIGIN, ""), cors_origins)
    return response


async def _apply(
    codec_fn: Callable[[Sequence[Payload]], Awaitable[list[Payload]]],
    cors_origins: list[str],
    request: web.Request,
) -> web.Response:
    """Generic handler: parse Payloads JSON, apply codec function, return Payloads JSON."""
    if request.content_type != "application/json":
        return _error_response(request, cors_origins, 415, "Expected application/json")

    try:
        payloads_proto = json_format.Parse(await request.read(), Payloads())
    except json_format.ParseError:
        return _error_response(request, cors_origins, 400, "Malformed Payloads JSON")

    try:
        result_payloads = await codec_fn(payloads_proto.payloads)
    except StorageFileNotFoundError as exc:
        log.error(f"Codec storage lookup failed: {exc}")
        return _error_response(request, cors_origins, 404, "Storage object not found")
    except (OSError, FileNotFoundError) as exc:
        log.error(f"Codec I/O error: {exc}")
        return _error_response(request, cors_origins, 502, "Storage I/O error")

    result_proto = Payloads(payloads=result_payloads)

    response = web.Response()
    _set_cors_headers(response, request.headers.get(hdrs.ORIGIN, ""), cors_origins)
    response.content_type = "application/json"
    response.text = json_format.MessageToJson(result_proto)
    return response


def build_codec_server(codec: StoragePayloadCodec, cors_origins: list[str]) -> web.Application:
    """Build an aiohttp application implementing the Temporal codec server protocol.

    Args:
        codec: The payload codec to use for encode/decode operations.
        cors_origins: Allowed CORS origins (e.g. ``["http://localhost:8233"]``).

    Returns:
        A configured aiohttp web application ready to run.
    """
    cors_handler = _make_cors_handler(cors_origins)
    application = web.Application()
    application.add_routes(
        [
            web.post("/encode", partial(_apply, codec.encode, cors_origins)),
            web.post("/decode", partial(_apply, codec.decode, cors_origins)),
            web.options("/encode", cors_handler),
            web.options("/decode", cors_handler),
        ]
    )
    log.info(f"Codec server configured — CORS origins: {cors_origins}")
    return application
