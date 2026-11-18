"""Check that a running server refuses a method shipping Python, with the custom-code 501.

Whether the server may run a method's own `.py` files is a matter of configuration: it runs them only when PipeFunc
executes in the Daytona sandbox (`is_pipe_func_sandbox_hosted` in `pipelex/config.py`). The image ships that
configuration at `/root/.pipelex/`, outside any project, so a drift in what the image ships could open the gate on the
published image alone while every route test stays green. This script sends `POST /v1/validate` a method holding a
`.py` file and passes only when the server answers the 501 problem `pipelex.deployment.custom_code_requires_sandbox`,
domain `operator`, with `params.origin` `bundle`. `make docker-smoke` runs it against the container it starts.

It needs nothing but the standard library, so it runs on a bare runner without the member's environment.

Usage:
    python scripts/check_custom_code_gate.py http://127.0.0.1:18081
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, cast

_EXPECTED_STATUS = 501
EXPECTED_PROBLEM = {
    "code": "pipelex.deployment.custom_code_requires_sandbox",
    "domain": "operator",
    "params": {"origin": "bundle"},
}

_GREET_MTHDS = """\
domain = "greeting"
main_pipe = "greet"

[pipe.greet]
type = "PipeCompose"
description = "Greet"
inputs = { text = "Text" }
output = "Text"
template = "Hello $text"
"""

REQUEST_BODY = {"files": {"greet.mthds": _GREET_MTHDS, "helpers/tool.py": "VALUE = 1\n"}}


def _post_validate(validate_url: str) -> tuple[int, Any]:
    """Send the method to the validate route and return the status with the decoded body, whatever the status."""
    request = urllib.request.Request(  # noqa: S310 - the URL is the smoke container's own
        validate_url,
        data=json.dumps(REQUEST_BODY).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - the URL is the smoke container's own
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw_body)
        except json.JSONDecodeError:
            return exc.code, raw_body


def refusal_mismatch(*, status: int, body: Any) -> str | None:
    """Say how an answer differs from the custom-code 501, or return None when it is that refusal."""
    if status != _EXPECTED_STATUS:
        return f"expected status {_EXPECTED_STATUS}, got {status}"
    if not isinstance(body, dict):
        return "the refusal is not a JSON problem object"
    problem = cast("dict[str, Any]", body)
    mismatches = {field: problem.get(field) for field, expected in EXPECTED_PROBLEM.items() if problem.get(field) != expected}
    if mismatches:
        return f"expected {EXPECTED_PROBLEM}, got {mismatches}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that a running pipelex-api server refuses a method shipping Python.")
    parser.add_argument("base_url", help="The server's base URL, without the /v1 prefix")
    args = parser.parse_args()

    validate_url = f"{args.base_url.rstrip('/')}/v1/validate"
    try:
        status, body = _post_validate(validate_url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Custom-code gate check FAILED: cannot read {validate_url}: {exc}")
        return 1
    print(f"POST {validate_url} with a .py file: {status} {json.dumps(body)}")
    mismatch = refusal_mismatch(status=status, body=body)
    if mismatch is not None:
        print(f"Custom-code gate check FAILED: {mismatch}.")
        return 1
    print("The server refuses a method shipping Python with the custom-code 501.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
