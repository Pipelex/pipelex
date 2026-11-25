"""Export the FastAPI-generated OpenAPI schema to the committed YAML artifact.

The committed file (`docs/api-server/openapi/pipelex-api.openapi.yaml` at the repository root,
published on the pipelex docs site beside the server's pages) is the layer-2 contract of the MTHDS
Protocol nesting (MTHDS Protocol ⊂ Pipelex API ⊂ Pipelex hosted API): the five protocol routes are
tagged `x-mthds-protocol: true`, and the untagged Pipelex extensions (`/resolve`, `/codegen`,
`/pipe-io`, `/models/check`, `/lint`, `/format`, and the storage transport, `/resolve-storage-url/bulk` and
`/storage/{key}`) ride alongside.

Usage:
    python scripts/export_openapi.py ../docs/api-server/openapi/pipelex-api.openapi.yaml
    python scripts/export_openapi.py --check ../docs/api-server/openapi/pipelex-api.openapi.yaml

`--check` exits non-zero when the committed artifact drifts from the schema the
app currently generates — `make openapi-check`, which the gate (`make agent-check`, here or at the
repository root) runs.

The artifact describes the server as it boots by default, so the export reads the app under the default
`AUTH_MODE` and with `TRUST_FORWARDED_IDENTITY_HEADERS` off, whatever the environment or a `.env` says: both
decide which routes are mounted, and `api/Makefile` exports `.env` into every target. Export and check are
then the same on every machine.
"""

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import cast

import yaml
from fastapi import FastAPI

# Imported first, for its side effect: pipelex loads the home and project `.env` files into the environment, overriding
# it, the first time this module is imported. The defaults below are set after that load, so no `.env` undoes them.
from pipelex.system import environment as _pipelex_environment  # noqa: F401  # pyright: ignore[reportUnusedImport]

from pipelex_api.security import AUTH_MODE_ENV_VAR, TRUST_FORWARDED_IDENTITY_HEADERS_ENV, AuthMode

_GENERATED_HEADER = "# GENERATED FILE — do not edit by hand. Regenerate with `make openapi-export`.\n"
_EXPORT_HINT = "`make openapi-export` in api/ (`make -C api openapi-export` from the repository root)"


def _documented_app() -> FastAPI:
    """The app as it boots under the default authentication mode and without trusting forwarded identity.

    `pipelex_api.main` selects its authentication and mounts its routes when it is imported, so it is imported here,
    once both variables hold their defaults, rather than at the top of this module.
    """
    os.environ[AUTH_MODE_ENV_VAR] = AuthMode.NONE
    os.environ[TRUST_FORWARDED_IDENTITY_HEADERS_ENV] = "false"
    main_module = importlib.import_module("pipelex_api.main")
    return cast("FastAPI", main_module.fastapi_app)


def render_openapi_yaml() -> str:
    schema = _documented_app().openapi()
    body = yaml.safe_dump(schema, sort_keys=False, allow_unicode=True, width=120)
    return _GENERATED_HEADER + body


def main() -> int:
    parser = argparse.ArgumentParser(description="Export (or drift-check) the committed OpenAPI artifact.")
    parser.add_argument("target", type=Path, help="Path of the committed OpenAPI YAML artifact")
    parser.add_argument("--check", action="store_true", help="Compare a fresh export against the committed artifact; exit 1 on drift")
    args = parser.parse_args()

    rendered = render_openapi_yaml()
    target: Path = args.target

    if args.check:
        if not target.exists():
            print(f"OpenAPI drift check FAILED: {target} does not exist. Run {_EXPORT_HINT}.")
            return 1
        if target.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI drift check FAILED: {target} is stale. Run {_EXPORT_HINT} and commit the result.")
            return 1
        print(f"OpenAPI artifact is up to date: {target}")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
