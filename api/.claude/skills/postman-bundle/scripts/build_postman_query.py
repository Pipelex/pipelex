#!/usr/bin/env python3
"""Build a runnable Postman request from a Pipelex MTHDS bundle and push it live.

Mirrors ``pipelex run bundle <path>`` resolution: given a bundle directory (or a
single ``.mthds`` file), it finds the bundle file(s), extracts ``main_pipe``,
loads the sibling ``inputs.json``, and inserts a ready-to-run request into the
live "Pipelex FastAPI" Postman collection under ``Bundles/<bundle>/``.

Requests are generated per bundle (configurable via ``--endpoint``):
``Execute (sync)`` -> ``POST /v1/execute``, ``Start (async)`` ->
``POST /v1/start``, ``Validate (dry-run)`` -> ``POST /v1/validate``,
``Resolve (crate)`` -> ``POST /v1/resolve``, ``Codegen (types)`` ->
``POST /v1/codegen``, and the three bundle build routes ->
``POST /v1/build/{inputs,output,runner}``. Only execute/start trigger
inference — every other endpoint parses/loads/dry-runs with zero cost. All use
the collection's ``{{base_url}}`` and inherit its ``{{auth_token}}`` bearer auth.

The async ``Start (async)`` body additionally carries ``callback_urls`` — the
webhook(s) the runner POSTs the finished result to. It is resolved from
``--callback-url``, else ``CALLBACK_URL`` in the environment / ``.env``; a start
request fails fast (asking for one) if none is found.

File/document inputs are NOT uploaded. Any local (non-http) ``url`` in
inputs.json is copied verbatim and reported so you can swap in a real URL before
running. Run this against a self-contained bundle (concepts/structures declared
inline in the .mthds) — the API only receives the inline mthds_contents, not the
directory, so sibling Python structure classes are not available.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, NoReturn, cast

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 — fall back to regex extraction.
    tomllib = None  # type: ignore[assignment]

DEFAULT_COLLECTION_UID = "35082494-559c5753-885c-409a-af63-7647fe28d301"
POSTMAN_API_BASE = "https://api.getpostman.com"
DEFAULT_BUNDLE_FILE_NAME = "bundle.mthds"
DEFAULT_INPUTS_FILE_NAME = "inputs.json"
MTHDS_EXTENSION = ".mthds"
TOP_FOLDER_NAME = "Bundles"

# name -> (request display name, URL path segments, body kind)
# Body kind selects the request shape:
#   "run"          -> {pipe_code, mthds_contents, inputs} for the sync /execute
#   "start"        -> the same plus {callback_urls} for the async /start
#   "validate"     -> {mthds_contents, allow_signatures [, mthds_sources, render]}
#   "resolve"      -> {files: [{content, source}]} — the crate envelope
#   "codegen"      -> the crate envelope plus {kind, target}
#   "build_inputs" -> the crate envelope plus {pipe_ref, format, explicit}
#   "build_output" -> the crate envelope plus {pipe_ref, format}
#   "build_runner" -> the crate envelope plus {pipe_ref, allow_signatures}
# Only "run"/"start" trigger inference; every other kind is a free
# parse/load/dry-run on the server.
ENDPOINTS: dict[str, tuple[str, list[str], str]] = {
    "execute": ("Execute (sync)", ["v1", "execute"], "run"),
    "start": ("Start (async)", ["v1", "start"], "start"),
    "validate": ("Validate (dry-run)", ["v1", "validate"], "validate"),
    "resolve": ("Resolve (crate)", ["v1", "resolve"], "resolve"),
    "codegen": ("Codegen (types)", ["v1", "codegen"], "codegen"),
    "build-inputs": ("Build Inputs", ["v1", "build", "inputs"], "build_inputs"),
    "build-output": ("Build Output", ["v1", "build", "output"], "build_output"),
    "build-runner": ("Build Runner", ["v1", "build", "runner"], "build_runner"),
}

# Which endpoints need what. execute/start run a specific pipe with real inputs;
# the build routes target a specific pipe but take no inputs; validate and the
# crate routes (resolve/codegen) derive everything from the bundle text.
PIPE_CODE_ENDPOINTS = {"execute", "start", "build-inputs", "build-output", "build-runner"}
INPUTS_ENDPOINTS = {"execute", "start"}
SIGNATURE_ENDPOINTS = {"validate", "build-runner"}
CRATE_ENDPOINTS = {"resolve", "codegen"}

CODEGEN_TARGETS = ["ts-zod", "python-pydantic", "python-structures"]
OUTPUT_FORMATS = ["schema", "json", "python"]
INPUTS_FORMATS = ["json", "toml"]


def fail(msg: str) -> NoReturn:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# --- bundle resolution (mirrors `pipelex run bundle`) ---------------------


def resolve_bundle(raw_path: str, inputs_override: str | None) -> tuple[Path, list[Path], Path | None]:
    """Resolve a bundle path into (main_file, all_mthds_files, inputs_path).

    Directory mode auto-detects ``bundle.mthds`` (or the single ``*.mthds``) and
    a sibling ``inputs.json``, exactly like the CLI. File mode takes the .mthds
    as-is and only uses ``--inputs`` if given (the CLI does not auto-detect
    inputs in file mode).
    """
    target = Path(raw_path).expanduser()

    if target.is_dir():
        bundle_file = target / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            main_file = bundle_file
        else:
            mthds_files = sorted(target.glob(f"*{MTHDS_EXTENSION}"))
            if not mthds_files:
                fail(f"no {MTHDS_EXTENSION} bundle file found in directory '{raw_path}'")
            if len(mthds_files) > 1:
                names = ", ".join(path.name for path in mthds_files)
                fail(
                    f"multiple {MTHDS_EXTENSION} files in '{raw_path}' ({names}) and no "
                    f"{DEFAULT_BUNDLE_FILE_NAME}. Pass the .mthds file directly, or set a "
                    f"{DEFAULT_BUNDLE_FILE_NAME}, or override with --pipe."
                )
            main_file = mthds_files[0]

        # Send every .mthds in the directory (main first), mirroring how the CLI
        # adds the directory as a library dir so sibling bundles resolve.
        all_mthds = [main_file] + [path for path in sorted(target.glob(f"*{MTHDS_EXTENSION}")) if path != main_file]

        inputs_path: Path | None = None
        if inputs_override:
            inputs_path = Path(inputs_override).expanduser()
        else:
            candidate = target / DEFAULT_INPUTS_FILE_NAME
            if candidate.is_file():
                inputs_path = candidate
        return main_file, all_mthds, inputs_path

    if target.is_file() and target.suffix == MTHDS_EXTENSION:
        inputs_path = Path(inputs_override).expanduser() if inputs_override else None
        return target, [target], inputs_path

    fail(f"'{raw_path}' is not a {MTHDS_EXTENSION} file or directory")


def parse_bundle_meta(text: str) -> tuple[str | None, str | None]:
    """Extract (main_pipe, domain) from a .mthds bundle.

    Uses tomllib when available (the .mthds top level is valid TOML), falling
    back to a line-anchored regex so a non-standard bundle still yields a guess.
    """
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
            main_pipe = data.get("main_pipe")
            domain = data.get("domain")
            return (
                main_pipe if isinstance(main_pipe, str) else None,
                domain if isinstance(domain, str) else None,
            )
        except tomllib.TOMLDecodeError:
            pass
    main_match = re.search(r'(?m)^\s*main_pipe\s*=\s*"([^"]+)"', text)
    domain_match = re.search(r'(?m)^\s*domain\s*=\s*"([^"]+)"', text)
    return (
        main_match.group(1) if main_match else None,
        domain_match.group(1) if domain_match else None,
    )


# --- inputs ----------------------------------------------------------------


def load_inputs(path: Path | None) -> tuple[Any, list[str]]:
    """Load inputs.json verbatim and report any local (non-http) url values."""
    if path is None:
        return None, []
    if not path.is_file():
        fail(f"inputs file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"inputs file '{path}' is not valid JSON: {exc}")
    return data, collect_local_urls(data)


def collect_local_urls(value: Any, acc: list[str] | None = None) -> list[str]:
    """Walk a JSON value and collect ``url`` strings that are not http(s)."""
    if acc is None:
        acc = []
    if isinstance(value, dict):
        for key, val in cast("dict[str, Any]", value).items():
            if key == "url" and isinstance(val, str) and not val.startswith(("http://", "https://")):
                acc.append(val)
            else:
                collect_local_urls(val, acc)
    elif isinstance(value, list):
        for item in cast("list[Any]", value):
            collect_local_urls(item, acc)
    return acc


# --- callback urls (async /start only) --------------------------------------

CALLBACK_URL_ENV_VAR = "CALLBACK_URL"

# In the Postman push, the async-start callback rides a collection/environment
# variable — switchable alongside {{base_url}} and {{auth_token}} — never a
# baked-in URL. Only --run/--curl (real HTTP calls) need a resolved URL.
POSTMAN_CALLBACK_VAR = "{{callback_url}}"


def resolve_callback_urls(cli_values: list[str] | None) -> list[str]:
    """Resolve the async-start callback URL(s): --callback-url, then CALLBACK_URL.

    Order: explicit ``--callback-url`` (repeatable) wins; otherwise fall back to
    ``CALLBACK_URL`` from the process environment (``make`` exports ``.env``), then
    from a ``.env`` file found at or above the cwd (covers running the script
    directly). Returns an empty list when nothing is found — the caller decides
    whether that is fatal.
    """
    if cli_values:
        return cli_values
    from_env = os.environ.get(CALLBACK_URL_ENV_VAR)
    if from_env:
        return [from_env]
    from_dotenv = read_dotenv_value(CALLBACK_URL_ENV_VAR)
    if from_dotenv:
        return [from_dotenv]
    return []


def read_dotenv_value(key: str) -> str | None:
    """Read a single ``KEY=VALUE`` from the nearest ``.env`` (cwd upward).

    Minimal parser — enough to pick up ``CALLBACK_URL`` when the script is run
    directly (without ``make``, which would otherwise export ``.env`` for us).
    Skips blanks/comments, tolerates an ``export`` prefix, and strips matching
    surrounding quotes.
    """
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].lstrip()
            name, sep, value = stripped.partition("=")
            if not sep or name.strip() != key:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value or None
    return None


# --- Postman request construction -----------------------------------------


def build_run_body(
    pipe_code: str | None,
    mthds_contents: list[str],
    inputs: Any,
    callback_urls: list[str] | None = None,
) -> str:
    """Body for /execute and /start: pipe_code + mthds_contents + inputs.

    The async /start adds ``callback_urls`` — the webhook(s) the runner
    POSTs the finished result to. It is omitted for the sync /execute.
    """
    body: dict[str, Any] = {}
    if pipe_code:
        body["pipe_code"] = pipe_code
    body["mthds_contents"] = mthds_contents
    if inputs is not None:
        body["inputs"] = inputs
    if callback_urls:
        body["callback_urls"] = callback_urls
    return json.dumps(body, indent=2, ensure_ascii=False)


def build_validate_body(
    mthds_contents: list[str],
    allow_signatures: bool,
    *,
    mthds_sources: list[str] | None = None,
    render: list[str] | None = None,
) -> str:
    """Body for /validate — the skill-faithful wire shape.

    The endpoint takes no ``pipe_code`` and no ``inputs`` — it parses, loads, and
    dry-runs every pipe with mock inputs and zero inference, so it needs only the
    bundle text. This mirrors exactly what ``mthds-agent validate bundle <file>``
    sends through ``--runner api`` (see ``mthds-js`` ``MthdsApiClient.validate``):

    - ``mthds_contents`` — always.
    - ``allow_signatures`` — always present (real clients send the bool verbatim;
      ``false`` is the strict default).
    - ``mthds_sources`` — when provided, parallel to ``mthds_contents``; each entry
      names the owning file so server-side ``validation_errors[].source`` resolves.
    - ``render`` — the opt-in Pipelex-API presentation hint (e.g. ``["markdown"]``).
      A **skill** validates with the default Markdown view, so it sends
      ``render: ["markdown"]`` and reads the ``rendered_markdown`` the 200 carries; a
      **hook** validates with ``--format json`` and omits ``render`` (lean structured
      body). Pass ``--render markdown`` to reproduce the skill flow.
    """
    body: dict[str, Any] = {
        "mthds_contents": mthds_contents,
        "allow_signatures": allow_signatures,
    }
    if mthds_sources:
        body["mthds_sources"] = mthds_sources
    if render:
        body["render"] = render
    return json.dumps(body, indent=2, ensure_ascii=False)


def build_crate_body(
    mthds_contents: list[str],
    mthds_sources: list[str],
    *,
    codegen_kind: str | None = None,
    codegen_target: str | None = None,
) -> str:
    """Body for /resolve and /codegen — the crate routes' ``files[]`` envelope.

    Unlike validate's parallel ``mthds_contents[]``/``mthds_sources[]`` lists, the
    crate routes pair each content with its source in one ``{content, source}``
    entry (the shape the codegen spec pins). No ``pipe_code``, no ``inputs`` —
    the closure is the whole request. /codegen adds the two projection axes:
    ``kind`` (only ``types`` is served — input templates ride /build/inputs) and
    ``target`` (``ts-zod`` | ``python-pydantic`` | ``python-structures``).
    """
    body: dict[str, Any] = {}
    if codegen_kind:
        body["kind"] = codegen_kind
    if codegen_target:
        body["target"] = codegen_target
    body["files"] = [{"content": content, "source": source} for content, source in zip(mthds_contents, mthds_sources)]
    return json.dumps(body, indent=2, ensure_ascii=False)


def build_build_body(
    mthds_contents: list[str],
    mthds_sources: list[str],
    *,
    pipe_ref: str | None,
    allow_signatures: bool | None = None,
    output_format: str | None = None,
    inputs_format: str | None = None,
    explicit: bool | None = None,
) -> str:
    """Body for /build/{inputs,output,runner} — the SAME ``files[]`` closure envelope as
    /resolve and /codegen, plus a pipe selector.

    ``pipe_ref`` is the qualified ``domain.pipe_code`` and is optional on the wire
    (it defaults to the closure's ``main_pipe``); it is sent explicitly here so the
    generated query is unambiguous and stays correct if the bundle later declares
    several main_pipes.

    Each route projects one artifact for that pipe — an inputs template (``format``:
    json | toml, plus ``explicit``; /build/inputs only), an output representation
    (``format``: schema | json | python; /build/output only), or a runner script. No
    ``inputs`` on the wire — nothing runs.

    ``format`` is a per-route axis with a different vocabulary on each, so the two are
    threaded separately (``inputs_format`` vs ``output_format``) and only ever one is set.

    ``allow_signatures`` is sent only for /build/runner: it parameterizes the dry-run
    sweep, and the static /build/{inputs,output} projections dropped that sweep.
    """
    body: dict[str, Any] = {}
    if pipe_ref:
        body["pipe_ref"] = pipe_ref
    if allow_signatures is not None:
        body["allow_signatures"] = allow_signatures
    if output_format:
        body["format"] = output_format
    if inputs_format:
        body["format"] = inputs_format
    if explicit is not None:
        body["explicit"] = explicit
    body["files"] = [{"content": content, "source": source} for content, source in zip(mthds_contents, mthds_sources)]
    return json.dumps(body, indent=2, ensure_ascii=False)


def build_request_item(name: str, path_parts: list[str], body_raw: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": {"mode": "raw", "raw": body_raw, "options": {"raw": {"language": "json"}}},
            "url": {
                "raw": "{{base_url}}/" + "/".join(path_parts),
                "host": ["{{base_url}}"],
                "path": path_parts,
            },
            "description": description,
        },
        "response": [],
    }


# --- Postman collection upsert --------------------------------------------


def find_or_create_folder(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in items:
        if item.get("name") == name and "item" in item:
            return item
    folder: dict[str, Any] = {"name": name, "item": []}
    items.append(folder)
    return folder


def upsert_bundle_folder(collection: dict[str, Any], subfolder_name: str, requests: list[dict[str, Any]]) -> str:
    """Merge requests into the bundle's subfolder, matched by request name.

    A same-name request is replaced (fresh body), anything else in the folder is
    kept — so pushing `--endpoint codegen` doesn't wipe the Execute/Start pair
    pushed earlier, and two codegen targets (distinct display names) coexist.
    """
    top = find_or_create_folder(collection["item"], TOP_FOLDER_NAME)
    for item in top["item"]:
        if item.get("name") == subfolder_name and "item" in item:
            existing: list[dict[str, Any]] = item["item"]
            for request in requests:
                for index, existing_request in enumerate(existing):
                    if existing_request.get("name") == request["name"]:
                        existing[index] = request
                        break
                else:
                    existing.append(request)
            return "updated"
    top["item"].append({"name": subfolder_name, "item": requests})
    return "created"


def postman_request(uid: str, api_key: str, method: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"X-API-Key": api_key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{POSTMAN_API_BASE}/collections/{uid}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        fail(f"Postman {method} failed ({exc.code}): {detail}")
    except urllib.error.URLError as exc:
        fail(f"Postman {method} could not reach {POSTMAN_API_BASE}: {exc.reason}")


# --- direct run / curl (run the same query from Claude Code) ---------------

DEFAULT_BASE_URL = "http://127.0.0.1:8081"


def write_body_file(subfolder_name: str, body_raw: str) -> Path:
    """Persist the request body so curl can `--data @file` (no shell escaping)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", subfolder_name)
    path = Path(tempfile.gettempdir()) / f"run_bundle_{safe}.json"
    path.write_text(body_raw, encoding="utf-8")
    return path


def render_curl(base_url: str, token: str | None, path_parts: list[str], body_path: Path) -> str:
    url = base_url.rstrip("/") + "/" + "/".join(path_parts)
    lines = [f"curl -sS -X POST '{url}' \\", "  -H 'Content-Type: application/json' \\"]
    if token:
        lines.append(f"  -H 'Authorization: Bearer {token}' \\")
    lines.append(f"  --data @{body_path} | jq .")
    return "\n".join(lines)


def run_pipeline(base_url: str, token: str | None, path_parts: list[str], body_raw: str) -> tuple[int, str]:
    url = base_url.rstrip("/") + "/" + "/".join(path_parts)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body_raw.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # The API renders errors as RFC 7807 problem+json — surface the body as-is.
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        fail(f"could not reach {url}: {exc.reason}. Is the API running? Start it with `make run`.")


def pretty_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return text


# --- main ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve a Pipelex MTHDS bundle and either push a Postman query, emit curl, or run it."
    )
    parser.add_argument("bundle", help="Path to a bundle directory or a .mthds file")
    parser.add_argument("--inputs", help="Override inputs JSON path (default: auto-detect inputs.json in a directory)")
    parser.add_argument("--pipe", help="Override main_pipe (sets pipe_code). Ignored by --endpoint validate.")
    parser.add_argument(
        "--callback-url",
        action="append",
        metavar="URL",
        help=(
            "Webhook URL for the async /start callback (repeatable; only used by the start "
            "endpoint). Falls back to CALLBACK_URL in the environment / .env. Required whenever start "
            "is the endpoint being built or run."
        ),
    )
    parser.add_argument(
        "--allow-signatures",
        action="store_true",
        help=(
            "(validate + build-runner) Tolerate unimplemented pipe signatures instead of rejecting the bundle. "
            "Parameterizes the dry-run sweep, so the static build-inputs/build-output projections do not take it. "
            "Default: strict."
        ),
    )
    parser.add_argument(
        "--target",
        choices=CODEGEN_TARGETS,
        help=(
            "(codegen only) Projection target: ts-zod (zod schemas + inferred types), python-pydantic "
            "(self-contained BaseModels), or python-structures (Pipelex runtime StructuredContent classes). "
            "Required when --endpoint codegen."
        ),
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMATS,
        default="schema",
        help="(build-output only) Output representation format (default: schema). `python` returns source text in `output_python`.",
    )
    parser.add_argument(
        "--inputs-format",
        choices=INPUTS_FORMATS,
        default="json",
        help=(
            "(build-inputs only) Inputs template encoding (default: json). `json` returns a parsed object in `inputs`; "
            "`toml` returns raw text in `inputs_toml`, carrying the per-key `# concept:` comments JSON cannot."
        ),
    )
    parser.add_argument(
        "--explicit",
        action="store_true",
        help=(
            "(build-inputs only) Emit the ceremonial {concept, content} envelope for every input instead of the "
            "default light shape (a bare string for a Text input, and so on)."
        ),
    )
    parser.add_argument(
        "--render",
        action="append",
        metavar="FORMAT",
        help=(
            "(validate only) Opt-in server-side view format to request, e.g. --render markdown. Adds `render` "
            "to the body so /validate returns a `rendered_markdown` view of the verdict — this is what a "
            "skill-driven validate (default Markdown) sends. Repeatable. Omit it for the lean structured body "
            "a hook reads (--format json)."
        ),
    )
    parser.add_argument(
        "--endpoint",
        choices=[*ENDPOINTS, "both"],
        default="both",
        help=(
            "Which endpoint(s) to target (default: both = execute + start). Besides the run pair, "
            "every choice is inference-free: 'validate' dry-runs the bundle, 'resolve' returns the "
            "normalized library crate, 'codegen' projects the crate into typed artifacts "
            "(needs --target), and 'build-inputs'/'build-output'/'build-runner' project one "
            "artifact for the requested pipe. For --run, 'both' runs execute (sync)."
        ),
    )
    parser.add_argument("--name", help="Override the per-bundle subfolder name (default: bundle domain or filename)")
    parser.add_argument("--collection-uid", default=DEFAULT_COLLECTION_UID, help="Target Postman collection UID")
    # Output mode (default: push to Postman). At most one of these.
    parser.add_argument("--dry-run", action="store_true", help="Print the request body; touch nothing")
    parser.add_argument("--curl", action="store_true", help="Emit a ready-to-run curl command; do not execute")
    parser.add_argument("--run", action="store_true", help="Execute the request against --base-url and print the response")
    # Only used by --run / --curl.
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL for --run/--curl (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--token", help="Bearer token for --run/--curl (omit when the server runs AUTH_MODE=none)")
    args = parser.parse_args()

    if sum([args.dry_run, args.curl, args.run]) > 1:
        fail("choose at most one of --dry-run, --curl, --run.")
    mode = "run" if args.run else "curl" if args.curl else "dry" if args.dry_run else "postman"

    api_key = os.environ.get("POSTMAN_API_KEY")
    if mode == "postman" and not api_key:
        fail("POSTMAN_API_KEY is not set. Run `source ~/.zshenv` (or add the key there), then retry.")

    selected = ["execute", "start"] if args.endpoint == "both" else [args.endpoint]
    # The single endpoint --run fires: 'both' is not meaningful for one run, so use
    # execute (sync), which waits for and returns the result.
    run_key = "execute" if args.endpoint == "both" else selected[0]
    # In --run mode only run_key actually fires, so build/require only its body.
    # Every other mode (postman/curl/dry) materializes all selected endpoints.
    active_keys = [run_key] if mode == "run" else selected

    needs_run = any(ENDPOINTS[key][2] == "run" for key in active_keys)
    needs_start = any(ENDPOINTS[key][2] == "start" for key in active_keys)
    needs_validate = any(ENDPOINTS[key][2] == "validate" for key in active_keys)
    needs_crate = any(key in CRATE_ENDPOINTS for key in active_keys)
    needs_signatures = any(key in SIGNATURE_ENDPOINTS for key in active_keys)
    # execute/start need pipe_code + inputs; the build routes need pipe_code only.
    needs_pipe = any(key in PIPE_CODE_ENDPOINTS for key in active_keys)
    needs_inputs = any(key in INPUTS_ENDPOINTS for key in active_keys)

    # /codegen requires the projection target up front — fail before any network work.
    if "codegen" in active_keys and not args.target:
        fail(f"--endpoint codegen requires --target <{'|'.join(CODEGEN_TARGETS)}>.")

    main_file, all_mthds, inputs_path = resolve_bundle(args.bundle, args.inputs)
    main_text = main_file.read_text(encoding="utf-8")
    main_pipe, domain = parse_bundle_meta(main_text)

    # `pipe_code` is required only by the run endpoints — /validate derives
    # everything it needs from the bundle text and takes no pipe_code.
    pipe_code = args.pipe or main_pipe
    if needs_pipe and not pipe_code:
        fail(
            f"could not determine main_pipe from '{main_file}'. Declare main_pipe in the bundle, "
            "or pass --pipe <pipe_code>."
        )

    # callback_urls belongs to the async /start endpoint only. In the Postman
    # push it is always the {{callback_url}} collection variable — switchable
    # alongside base_url/auth_token, never a baked-in URL. For --run/--curl/--dry
    # (real HTTP calls, or a preview of one) resolve a concrete URL from
    # --callback-url, then CALLBACK_URL (environment or .env); if none is found,
    # stop and ask the user for one.
    callback_urls: list[str] = []
    if needs_start:
        if mode == "postman":
            callback_urls = [POSTMAN_CALLBACK_VAR]
        else:
            callback_urls = resolve_callback_urls(args.callback_url)
            if not callback_urls:
                fail(
                    "the async /start endpoint requires callback_urls, but none was found. "
                    "Pass --callback-url <https-url>, or set CALLBACK_URL in your .env. If you don't "
                    "have one, ask the user for a callback URL (e.g. a https://webhook.site/... endpoint)."
                )

    mthds_contents = [path.read_text(encoding="utf-8") for path in all_mthds]

    # inputs (and their local-url warnings) matter only to the run endpoints;
    # every other endpoint ignores them, so don't load or warn otherwise.
    inputs: Any = None
    local_url_warnings: list[str] = []
    if needs_inputs:
        inputs, local_url_warnings = load_inputs(inputs_path)

    subfolder_name = args.name or domain or main_file.stem

    # Per-file sources, parallel to mthds_contents. /validate sends them as the
    # `mthds_sources` list; the crate routes pair them into `files[].source`.
    # Either way, server-side diagnostics name the owning file. `render` is the
    # opt-in presentation hint on /validate: a skill validates with the default
    # Markdown view (`--render markdown`), a hook omits it and reads the
    # structured body.
    mthds_sources = [path.name for path in all_mthds]
    render_formats: list[str] = []
    for raw_format in cast("list[str]", args.render or []):
        normalized = raw_format.strip().lower()
        if normalized and normalized not in render_formats:
            render_formats.append(normalized)

    # One body per endpoint kind in play (kinds are unique per endpoint, except
    # execute/start which share the run-request shape via "run"/"start").
    bodies: dict[str, str] = {}
    if needs_run:
        bodies["run"] = build_run_body(pipe_code, mthds_contents, inputs)
    if needs_start:
        bodies["start"] = build_run_body(pipe_code, mthds_contents, inputs, callback_urls=callback_urls)
    if needs_validate:
        bodies["validate"] = build_validate_body(
            mthds_contents,
            args.allow_signatures,
            mthds_sources=mthds_sources,
            render=render_formats or None,
        )
    if "resolve" in active_keys:
        bodies["resolve"] = build_crate_body(mthds_contents, mthds_sources)
    if "codegen" in active_keys:
        bodies["codegen"] = build_crate_body(mthds_contents, mthds_sources, codegen_kind="types", codegen_target=args.target)
    # The build routes take the QUALIFIED pipe ref (`domain.pipe_code`).
    #
    # Only `main_pipe` is guaranteed to live in the MAIN file's domain, so only it may be qualified
    # with that domain. A `--pipe` override is passed through verbatim: in a multi-file closure the
    # user may well be naming a pipe in a sibling domain, and stapling the main file's domain onto it
    # would silently select the wrong pipe (or 422 on a ref that doesn't exist). A bare `--pipe` still
    # resolves — the engine's lookup matches a bare code too — and the user can always qualify it.
    if args.pipe:
        pipe_ref = args.pipe
    elif domain and main_pipe:
        pipe_ref = f"{domain}.{main_pipe}"
    else:
        pipe_ref = main_pipe
    if "build-inputs" in active_keys:
        bodies["build_inputs"] = build_build_body(
            mthds_contents,
            mthds_sources,
            pipe_ref=pipe_ref,
            inputs_format=args.inputs_format,
            explicit=args.explicit or None,
        )
    if "build-output" in active_keys:
        bodies["build_output"] = build_build_body(mthds_contents, mthds_sources, pipe_ref=pipe_ref, output_format=args.output_format)
    if "build-runner" in active_keys:
        # Only /build/runner still runs the dry-run sweep that `allow_signatures` parameterizes.
        bodies["build_runner"] = build_build_body(
            mthds_contents, mthds_sources, pipe_ref=pipe_ref, allow_signatures=args.allow_signatures
        )

    print(f"Bundle:      {main_file}")
    print(f"mthds files: {', '.join(path.name for path in all_mthds)}")
    if needs_pipe:
        print(f"pipe_code:   {pipe_code}")
    if needs_inputs:
        print(f"inputs:      {inputs_path or 'none'}")
    if needs_start:
        print(f"callback:    {', '.join(callback_urls)}")
    if needs_signatures:
        print(f"signatures:  allow_signatures={args.allow_signatures}")
    if needs_validate:
        render_note = ", ".join(render_formats) or "none (structured-only, hook-style)"
        print(f"validate:    POST /v1/validate (no inference) — sources: {', '.join(mthds_sources)}")
        print(f"  render:    {render_note}")
    if needs_crate:
        print(f"crate:       files[] envelope — sources: {', '.join(mthds_sources)} (no inference)")
    if "codegen" in active_keys:
        print(f"codegen:     kind=types target={args.target}")
    if "build-output" in active_keys:
        print(f"format:      {args.output_format}")
    if local_url_warnings:
        warn_target = "the API" if mode in ("run", "curl") else "Postman"
        print("\nWARNING: inputs reference local (non-http) url(s) — file uploads are out of scope.")
        print(f"Replace these with real https URLs before running against {warn_target}:")
        for url in local_url_warnings:
            print(f"  - {url}")

    if mode == "dry":
        for kind, body in bodies.items():
            print(f"\n--- request body ({kind}) ---")
            print(body)
        return

    if mode == "curl":
        body_paths = {kind: write_body_file(f"{subfolder_name}-{kind}", body) for kind, body in bodies.items()}
        for path in body_paths.values():
            print(f"Body written to {path}")
        for key in selected:
            print(f"\n# {ENDPOINTS[key][0]}")
            print(render_curl(args.base_url, args.token, ENDPOINTS[key][1], body_paths[ENDPOINTS[key][2]]))
        return

    if mode == "run":
        # Only run_key (resolved above) actually fires — for 'both' that's execute (sync).
        name, path_parts, kind = ENDPOINTS[run_key]
        url = args.base_url.rstrip("/") + "/" + "/".join(path_parts)
        print(f"\nRunning {name}: POST {url}")
        status, response_text = run_pipeline(args.base_url, args.token, path_parts, bodies[kind])
        print(f"HTTP {status}")
        print(pretty_json(response_text))
        if status >= 400:
            sys.exit(1)
        return

    # mode == "postman"
    assert api_key is not None  # guaranteed above for the postman path
    trailer = (
        "Generated by the postman-bundle skill. Set `base_url` and `auth_token` in your "
        "Postman environment before running."
    )
    source_lines = f"- Source: `{main_file}`\n- .mthds files sent: {len(mthds_contents)}\n"

    def describe(key: str) -> str:
        """Per-endpoint Postman request description (shown in the collection)."""
        if key in ("execute", "start"):
            callback_note = (
                f"- callback_urls (Start only): `{', '.join(callback_urls)}` — set `callback_url` in your Postman environment\n"
                if needs_start
                else ""
            )
            return (
                f"Run the `{subfolder_name}` bundle (mirrors `pipelex run bundle`). Triggers REAL inference.\n\n"
                f"{source_lines}"
                f"- main_pipe: `{pipe_code}`\n"
                f"- inputs: {inputs_path or 'none'}\n"
                f"{callback_note}\n{trailer}"
            )
        if key == "validate":
            render_line = (
                f"- render: `{render_formats}` → response carries `rendered_markdown` (a skill-driven validate)\n"
                if render_formats
                else "- render: none (lean structured body — what a hook reads with --format json)\n"
            )
            return (
                f"Validate (dry-run) the `{subfolder_name}` bundle — parse, load, and dry-run every pipe "
                "with NO inference (free, no LLM cost).\n\n"
                f"{source_lines}"
                f"- mthds_sources: `{mthds_sources}`\n"
                f"- allow_signatures: {args.allow_signatures}\n"
                f"{render_line}\n"
                "Takes no pipe_code and no inputs. 200 discriminated on `is_valid`: the bundle blueprint, "
                f"graph spec, and per-pipe IO contracts — or structured validation_errors[]. {trailer}"
            )
        if key == "resolve":
            return (
                f"Resolve the `{subfolder_name}` library closure into its NORMALIZED CRATE — fully qualified "
                "refs, flattened refinement, materialized natives, fingerprint. NO inference, no dry-run sweep.\n\n"
                f"{source_lines}\n"
                "200 discriminated on `is_valid`: the canonical JSON crate on the valid arm, structured "
                f"validation_errors[] on the invalid arm. {trailer}"
            )
        if key == "codegen":
            return (
                f"Project the `{subfolder_name}` crate into typed artifacts (kind=types, target={args.target}) "
                "plus its codegen.lock. NO inference.\n\n"
                f"{source_lines}\n"
                "A client that writes the artifacts and lock verbatim reproduces a local `pipelex codegen types` "
                f"run byte-for-byte, so the offline `pipelex codegen check` passes. {trailer}"
            )
        # build-inputs / build-output / build-runner
        artifact = {
            "build-inputs": "the inputs JSON template",
            "build-output": f"the output representation (format={args.output_format})",
            "build-runner": "a runner script (plus the structures projection it imports)",
        }[key]
        if key == "build-runner":
            return (
                f"Generate {artifact} for pipe `{pipe_code}` of the `{subfolder_name}` bundle. Validates the "
                "bundle first (dry-run sweep scoped to the pipe, NO inference).\n\n"
                f"{source_lines}"
                f"- allow_signatures: {args.allow_signatures}\n\n"
                f"200 discriminated on `is_valid`. {trailer}"
            )
        return (
            f"Generate {artifact} for pipe `{pipe_code}` of the `{subfolder_name}` bundle. Static projection: "
            "resolves the closure and renders the pipe's declared IO — no dry-run sweep, NO inference.\n\n"
            f"{source_lines}\n"
            f"200 discriminated on `is_valid`. {trailer}"
        )

    def display_name(key: str) -> str:
        if key == "codegen":
            return f"Codegen (types → {args.target})"
        if key == "build-output":
            return f"Build Output ({args.output_format})"
        return ENDPOINTS[key][0]

    requests = [build_request_item(display_name(key), ENDPOINTS[key][1], bodies[ENDPOINTS[key][2]], describe(key)) for key in selected]
    print(f"requests:    {', '.join(display_name(key) for key in selected)} -> {TOP_FOLDER_NAME}/{subfolder_name}")

    envelope = postman_request(args.collection_uid, api_key, "GET", None)
    if "collection" not in envelope:
        fail(f"unexpected Postman GET response: {json.dumps(envelope)[:300]}")
    action = upsert_bundle_folder(envelope["collection"], subfolder_name, requests)
    postman_request(args.collection_uid, api_key, "PUT", envelope)

    vars_to_set = "base_url + auth_token" + (" + callback_url" if needs_start else "")
    print(f"\n{action.upper()} '{TOP_FOLDER_NAME}/{subfolder_name}' in the Pipelex FastAPI collection.")
    print(f"Open Postman (auto-syncs), set {vars_to_set}, and Send.")


if __name__ == "__main__":
    main()
