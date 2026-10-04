"""Check that a running server reports the release's version for itself and for the pipelex it runs.

The server and the library are released together under one version number, and the image is built from the
release commit, so `GET /v1/version` on a freshly built image must report that number twice: as
`implementation_version` (the `pipelex-api` distribution) and as `runtime_version` (the `pipelex` it runs).
`make docker-smoke` runs this against the container it starts.

It needs nothing but the standard library, so it runs on a bare runner without the member's environment.

Usage:
    python scripts/check_served_version.py http://127.0.0.1:18081 --version 0.71.0
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

_VERSION_FIELDS = ("implementation_version", "runtime_version")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the versions a running pipelex-api server reports.")
    parser.add_argument("base_url", help="The server's base URL, without the /v1 prefix")
    parser.add_argument("--version", required=True, help="The version both fields must report")
    args = parser.parse_args()

    version_url = f"{args.base_url.rstrip('/')}/v1/version"
    try:
        with urllib.request.urlopen(version_url, timeout=10) as response:  # noqa: S310 - the URL is the smoke container's own
            version_info = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Served-version check FAILED: cannot read {version_url}: {exc}")
        return 1
    print(f"{version_url}: {json.dumps(version_info)}")
    mismatches = {field: version_info.get(field) for field in _VERSION_FIELDS if version_info.get(field) != args.version}
    if mismatches:
        print(f"Served-version check FAILED: expected {args.version} for {', '.join(_VERSION_FIELDS)}, got {mismatches}.")
        return 1
    print(f"The server reports pipelex-api {args.version} running pipelex {args.version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
