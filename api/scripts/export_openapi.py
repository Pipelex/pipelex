"""Export the FastAPI-generated OpenAPI schema to the committed YAML artifact.

The committed file (`docs/api-server/openapi/pipelex-api.openapi.yaml` at the repository root,
published on the pipelex docs site beside the server's pages) is the layer-2 contract of the MTHDS
Protocol nesting (MTHDS Protocol ⊂ Pipelex API ⊂ Pipelex hosted API): the five protocol routes are
tagged `x-mthds-protocol: true`, the build tooling extensions ride alongside, and the non-contract
storage routes (`/upload`, `/resolve-storage-url`) are documented as such in their descriptions.

Usage:
    python scripts/export_openapi.py ../docs/api-server/openapi/pipelex-api.openapi.yaml
    python scripts/export_openapi.py --check ../docs/api-server/openapi/pipelex-api.openapi.yaml

`--check` exits non-zero when the committed artifact drifts from the schema the
app currently generates — `make openapi-check`, which the gate (`make agent-check`, here or at the
repository root) runs.
"""

import argparse
import sys
from pathlib import Path

import yaml

from pipelex_api.main import fastapi_app

_GENERATED_HEADER = "# GENERATED FILE — do not edit by hand. Regenerate with `make openapi-export`.\n"
_EXPORT_HINT = "`make openapi-export` in api/ (`make -C api openapi-export` from the repository root)"


def render_openapi_yaml() -> str:
    schema = fastapi_app.openapi()
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
