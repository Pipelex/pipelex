"""CLI entry point for the Temporal codec server.

Usage::

    python -m pipelex.temporal.codec.codec_server_cli
    python -m pipelex.temporal.codec.codec_server_cli --port 8082
    python -m pipelex.temporal.codec.codec_server_cli --cors-origin http://localhost:8233 --cors-origin https://cloud.temporal.io
"""

from __future__ import annotations

from typing import Annotated

import typer
from aiohttp import web

from pipelex import log
from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.temporal.codec.codec_factory import make_codec_from_config
from pipelex.temporal.codec.codec_server import build_codec_server
from pipelex.temporal.exceptions import TemporalConfigError
from pipelex.tools.misc.toml_utils import load_toml_from_path

app = typer.Typer()

DEFAULT_CORS_ORIGINS = ["http://localhost:8233"]


@app.command()
def configure(
    project: Annotated[str | None, typer.Argument(help="The project name if you don't want to get it from pyproject.toml")] = None,
    host: Annotated[str, typer.Option(help="Host to bind the codec server to")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to bind the codec server to")] = 8081,
    cors_origin: Annotated[list[str] | None, typer.Option(help="Allowed CORS origin (repeatable)")] = None,
) -> None:
    """Start the Temporal codec server for Web UI payload decoding."""
    if project is None:
        pyproject = load_toml_from_path(path="pyproject.toml")
        project = pyproject.get("project", {}).get("name") or pyproject.get("tool", {}).get("poetry", {}).get("name")
        if not project:
            msg = "Project name not found in pyproject.toml"
            raise ValueError(msg)

    Pipelex.make(temporal_enabled=True)

    payload_codec_config = get_config().temporal.payload_codec_config
    if not payload_codec_config.is_enabled:
        msg = (
            "Payload codec is not enabled in the config (temporal.payload_codec_config.is_enabled = false). "
            "Enable it in your pipelex.toml before starting the codec server."
        )
        raise TemporalConfigError(msg)

    codec = make_codec_from_config()
    cors_origins = cors_origin or DEFAULT_CORS_ORIGINS
    application = build_codec_server(codec=codec, cors_origins=cors_origins)

    log.info(f"Starting Temporal codec server on {host}:{port}")
    web.run_app(application, host=host, port=port)


if __name__ == "__main__":
    app()
