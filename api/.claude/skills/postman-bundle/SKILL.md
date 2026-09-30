---
name: postman-bundle
description: >-
  Turn a Pipelex MTHDS bundle into an API request against any bundle-shaped pipelex-api route — push it
  as a ready-to-run query into the live "Pipelex FastAPI" Postman collection, emit a curl command,
  execute it directly, or just preview the body. Covers the whole bundle surface: run (/v1/execute,
  /v1/start), dry-run validate (/v1/validate — no inference, no cost), crate resolution (/v1/resolve),
  typed codegen (/v1/codegen — ts-zod, python-pydantic, python-structures), and the per-pipe build
  projections (/v1/build/inputs, /v1/build/output, /v1/build/runner). Use this whenever the user points
  at a bundle directory or a .mthds file (often with an inputs.json) and wants to run, validate,
  resolve, codegen, or otherwise test it via the API — e.g. "make a Postman query for this bundle",
  "run the fashion_moodboard bundle against the API", "validate this bundle via the API", "resolve this
  bundle to a crate", "codegen this bundle", "generate the TypeScript types for this method over the
  API", "test /v1/resolve on this bundle", "build the inputs template via the API", "give me the curl
  for this bundle", or just "postman" said alongside a bundle path. It resolves the bundle exactly like
  `pipelex run bundle <path>` (auto-detects bundle.mthds / the single .mthds, reads main_pipe, loads the
  sibling inputs.json). Trigger it even when the user does not name the endpoint or the word "skill".
---

# Postman Bundle

Create runnable API requests for one Pipelex MTHDS bundle and push them into the live **Pipelex FastAPI** collection (or emit curl, or run them directly), so the user can exercise any bundle-shaped endpoint against a Pipelex API server. The query resolves the bundle the same way the CLI's `pipelex run bundle <path>` does.

This is a focused, one-bundle-at-a-time tool. It is **not** the full collection sync — for diffing the whole API surface against the code, that's the separate `/update-postman` command.

## Endpoint cheat sheet

| `--endpoint` | Route | Body envelope | Needs a pipe? | Needs `inputs`? | Inference? |
|---|---|---|---|---|---|
| `execute` | `POST /v1/execute` | run (`pipe_code`) | yes | yes | **YES — costs money** |
| `start` | `POST /v1/start` | run + `callback_urls` | yes | yes | **YES — costs money** |
| `validate` | `POST /v1/validate` | `mthds_contents` | no | no | no (free dry-run) |
| `resolve` | `POST /v1/resolve` | `files[]` crate | no | no | no (free) |
| `codegen` | `POST /v1/codegen` | `files[]` crate + `kind`/`target` | no | no | no (free) |
| `build-inputs` | `POST /v1/build/inputs` | `files[]` + `pipe_ref` + `format`/`explicit` | optional | no | no (free) |
| `build-output` | `POST /v1/build/output` | `files[]` + `pipe_ref` + `format` | optional | no | no (free) |
| `build-runner` | `POST /v1/build/runner` | `files[]` + `pipe_ref` + `allow_signatures` | optional | no | no (free) |

Every non-run endpoint answers with the **`/validate` verdict discipline**: a produced verdict is always a `200` discriminated on `is_valid` — the artifact on the valid arm, structured `validation_errors[]` on the invalid arm. Non-2xx is reserved for no-verdict conditions (request-shape `422`, auth `401`/`403`, server `5xx`), rendered as RFC 7807 `problem+json`.

## What it produces in Postman

For the bundle the user names, it upserts requests into the collection under:

```
Bundles/
  <bundle>/            (named by the bundle's `domain`, or the filename)
    Execute (sync)             Start (async)             Validate (dry-run)
    Resolve (crate)            Codegen (types → <target>)
    Build Inputs               Build Output (<format>)   Build Runner
```

Which requests appear depends on `--endpoint`: the default `both` is `execute` + `start`; every other endpoint is pushed alone. Pushes **merge by request name** — pushing `--endpoint codegen` doesn't wipe an Execute/Start pair pushed earlier, and two codegen targets (distinct names) coexist. Requests use the collection variable `{{base_url}}` and inherit the collection's `{{auth_token}}` bearer auth (and the **Start** request's `callback_urls` is the `{{callback_url}}` variable), so the same query works against a local or hosted server by switching the Postman environment.

(The top folder used to be `Run Bundle/` — if a stale folder by that name lingers in the collection, it can be deleted.)

## The two request envelopes

**Run + validate routes** carry the bundle as parallel lists — `mthds_contents` (full text of each `.mthds` file, main one first) plus, on `/validate`, `mthds_sources` (one filename per content, so `validation_errors[].source` names the owning file):

```json
{
  "pipe_code": "<the bundle's main_pipe>",
  "mthds_contents": ["<file text>", "..."],
  "inputs": { "...": "inputs.json copied verbatim" },
  "allow_signatures": false
}
```

(`pipe_code` and `inputs` ride execute/start only; `allow_signatures` rides validate.)

**Crate + build routes** (`resolve`, `codegen`, `build-*`) pair each content with its source in one `files[]` entry — the envelope the codegen spec pins. No `inputs`; the closure is the whole request. The build routes add a `pipe_ref` (the **qualified** `domain.pipe_code`; optional on the wire, defaulting to the closure's `main_pipe` — this skill always sends it explicitly):

```json
{
  "kind": "types",
  "target": "ts-zod",
  "files": [{ "content": "<file text>", "source": "<file name>" }]
}
```

(`kind`/`target` are codegen-only; `pipe_ref` is build-only.) The **start** body additionally carries `callback_urls` (see [Callback URLs](#callback-urls-the-async-start-endpoint)). The **validate** body optionally carries `render` (see below).

## Validate = the API's dry-run

`POST /v1/validate` is the API's dry-run: it parses, loads, and dry-runs every pipe with mock inputs and **zero inference** (no LLM calls, no cost), then returns the validated bundle blueprint, a `graph_spec`, and per-pipe input/output JSON-Schema `pipe_io_contracts`. It confirms the whole pipeline wires up without ever running it — the safe, free counterpart to `execute`/`start`. Reach for it to "just check" or "dry-run" a bundle.

- **`main_pipe` is optional for `/validate`.** A bundle with no `main_pipe` still validates (200, `is_valid: true`) — you just get `graph_spec: null`. `--pipe` is ignored.
- **`allow_signatures`** (`--allow-signatures`) tolerates unimplemented pipe signatures instead of rejecting the bundle (each dry-runs trivially by minting a mock). Useful for in-progress bundles. It parameterizes the **dry-run sweep**, so it rides `validate` and `build-runner` only — the static `build-inputs`/`build-output` projections dropped the sweep and do not accept it. Default strict.
- **`render`** (`--render markdown`) opts into a server-rendered Markdown view of the verdict, riding the 200 on both arms as `rendered_markdown`. This is what a **skill**-driven validate sends; a **hook** omits it and reads the structured `is_valid`. The structured fields stay the contract; the Markdown is the view.

## Resolve & Codegen (the crate routes)

**`POST /v1/resolve`** resolves the library closure into its **normalized crate** — fully qualified refs, flattened refinement, materialized natives, fingerprint set. It runs no dry-run sweep (runnability is `/validate`'s vocabulary). The valid arm carries the canonical JSON crate — the same bytes `pipelex resolve --format json` prints, so a fingerprint computed from either surface agrees.

**`POST /v1/codegen`** resolves the closure the same way, then projects the crate through two explicit axes: `kind` (only `types` is served — input templates ride `/build/inputs` instead) × `target`:

- `ts-zod` — zod schemas + inferred TypeScript types
- `python-pydantic` — self-contained pydantic BaseModels
- `python-structures` — Pipelex runtime `StructuredContent` classes (a Pipelex extension)

The valid arm carries the **stamped** artifact set plus its `codegen.lock`: a client that writes them verbatim reproduces a local `pipelex codegen types` run **byte-for-byte** and passes the offline `pipelex codegen check`. There is deliberately no server-side check route (the drift check is offline by design). An unknown `kind`/`target`, or a `pipe_ref` on the concept-set-wide `types`, is a request-shape `422`.

`--target` is **required** for codegen — there is no default; ask the user which consumer they're generating for if unclear. The request envelope also accepts a `method_ref` instead of `files[]`, but the server answers `501` until server-side method-registry resolution exists — this skill always sends `files[]`.

## Build routes (per-pipe projections)

`POST /v1/build/{inputs,output,runner}` project one artifact for one pipe of the closure, with no inference. They ride the same `files[]` closure selector as the crate routes plus a `pipe_ref` — resolved here from the bundle's `domain` + `main_pipe`, or from `--pipe`.

`build-inputs` and `build-output` are **static**: they resolve the closure and read the pipe's *declared* IO — no dry-run sweep, so a valid verdict from them is not a promise the pipe runs (ask `validate` for that). `build-runner` keeps the sweep, because a runner script *is* that promise.

- **`build-inputs`** → the inputs template for the pipe (what an `inputs.json` should look like). The valid arm carries `inputs` (a parsed object) for the default `format: json`, or `inputs_toml` (raw text) for `format: toml`; `explicit: true` swaps the light values for the ceremonial `{concept, content}` envelopes.
- **`build-output`** → the pipe's output representation; `--output-format schema|json|python` (default `schema`). `schema`/`json` land in `output` (a parsed object); `python` lands in `output_python` (source text).
- **`build-runner`** → a Python runner script spelling its imports with the **emitted** class names, plus the `structures` projection it imports from (stamped `structures.py` + `codegen.lock`, to write into a `structures/` directory beside the script) — matching what a local `pipelex build runner` scaffolds. A pipe recorded SKIPPED by the sweep (unresolved cross-package dependency) is a request-shape `422`.

## Callback URLs (the async `start` endpoint)

`/v1/start` is fire-and-forget: it returns a `run_id` immediately and POSTs the finished result to a webhook later, so a `start` request **must** carry `callback_urls`.

**Postman push (default mode) always uses the `{{callback_url}}` collection variable** — never a baked-in URL. The pushed body is `"callback_urls": ["{{callback_url}}"]`, so the callback is switchable in the Postman environment right alongside `base_url` and `auth_token` (local vs hosted). Nothing to resolve — just tell the user to set `callback_url` in their Postman environment (a `https://webhook.site/...` endpoint is the easy way to watch the result land).

**`--run` / `--curl` (a real HTTP call, or a preview of one) need a concrete URL.** Resolution order there:

1. **`--callback-url <url>`** (repeatable — the field is a JSON list; a single URL is the common case).
2. **`CALLBACK_URL`** in the environment or the repo `.env`. `make` exports `.env`; the script also reads `.env` directly when invoked outside `make`.
3. **Ask the user.** If neither is set, the script stops with a clear error — ask for a callback URL and re-run with `--callback-url`.

This only affects `start` — no other endpoint takes `callback_urls`. The API's SSRF guard rejects loopback/private/metadata hosts, so a `localhost` callback won't validate — use a public `https://` URL.

## How to run it

From the `pipelex-api` repo root, the make targets are the convenient wrapper (they run the script with the project venv):

```bash
make bundle-run      BUNDLE=<dir|.mthds>                 # POST to a running API, print the response
make bundle-validate BUNDLE=<dir|.mthds>                 # dry-run validate via /v1/validate (free)
make bundle-resolve  BUNDLE=<dir|.mthds>                 # resolve to the normalized crate (free)
make bundle-codegen  BUNDLE=<dir|.mthds> TARGET=ts-zod   # project typed artifacts + lock (free)
make bundle-curl     BUNDLE=<dir|.mthds>                 # emit a ready-to-run curl
make bundle-postman  BUNDLE=<dir|.mthds>                 # push request(s) into the Postman collection
make bundle-dry      BUNDLE=<dir|.mthds>                 # print the request body only
# optional: ENDPOINT=execute|start|validate|resolve|codegen|build-inputs|build-output|build-runner|both
#           PIPE=<code>  INPUTS=<path>  NAME=<folder>  ALLOW_SIGNATURES=1  TARGET=<codegen target>
#           OUTPUT_FORMAT=schema|json|python  CALLBACK_URL=<url>  BASE_URL=<url>  TOKEN=<bearer>  ARGS=<extra>
```

`bundle-validate` / `bundle-resolve` / `bundle-codegen` hardcode `--run` with their endpoint (they're free and safe to run live). The build routes ride the generic targets via `ENDPOINT=`, e.g. `make bundle-run ENDPOINT=build-inputs`, `make bundle-postman ENDPOINT=build-runner`, `make bundle-curl ENDPOINT=build-output OUTPUT_FORMAT=json`.

Under the hood it's one script that resolves the bundle once and sends the request to one of four sinks. `<bundle-path>` is a bundle **directory** (preferred) or a single `.mthds` file. Call the script directly for a path outside the repo or finer control:

**Push into the Postman collection** (default). Source the env first so the Postman key is present (it lives in `~/.zshenv`):

```bash
source ~/.zshenv 2>/dev/null
python3 .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> [--endpoint <ep>] [--target <t>]
```

After a successful push, tell the user it's in Postman (it auto-syncs), and that they should set `base_url` and `auth_token` in their Postman environment, then Send.

**Run it yourself from Claude Code** — POSTs the exact same body to a running API and prints the response:

```bash
python3 .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint <ep>
# defaults to http://127.0.0.1:8081 and no auth (AUTH_MODE=none). Override:
#   --base-url https://api.pipelex.com   --token <bearer>
```

The API must be up — start it locally with `make run` first. **Heads-up: only `execute`/`start` trigger real inference (cost + latency)** — confirm the user wants a live run for those. Every other endpoint is free and safe to fire without confirmation:

```bash
python3 .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint validate
python3 .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint resolve
python3 .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint codegen --target python-pydantic
python3 .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint build-inputs
```

**Emit a curl command** (`--curl`) — writes the body to a temp file and prints a `curl --data @file`, so the multi-line contents never need shell escaping. **Preview only** (`--dry-run`) — print the request body, touch nothing.

Useful options (apply across modes):

| Option | When to use |
|---|---|
| `--endpoint <ep>` | Pick the endpoint (see cheat sheet). Default `both` (= execute + start) for Postman/curl; `--run both` runs `execute`. |
| `--target <t>` | (codegen only, **required**) `ts-zod`, `python-pydantic`, or `python-structures`. |
| `--output-format <f>` | (build-output only) `schema` (default), `json`, or `python`. |
| `--allow-signatures` | (validate + build routes) Tolerate unimplemented pipe signatures. Default strict. |
| `--render <fmt>` | (validate only) Opt-in server-side view, e.g. `--render markdown` → response carries `rendered_markdown` (what a skill-driven validate sends). Omit for the lean structured body a hook reads. Repeatable. |
| `--inputs <path>` | Inputs JSON lives elsewhere, or you point at a `.mthds` file directly (file mode does not auto-detect inputs). execute/start only. |
| `--pipe <pipe_code>` | The bundle has no `main_pipe`, or you want a different pipe. Used by execute/start (as `pipe_code`) and the build routes (qualified into `pipe_ref`); ignored by validate/resolve/codegen. |
| `--callback-url <url>` | (start only) Webhook the async result is POSTed to. Repeatable. Falls back to `CALLBACK_URL` in env/`.env`. |
| `--base-url` / `--token` | Target server + bearer for `--run`/`--curl`. |
| `--name <folder>` | Override the per-bundle Postman subfolder name. |

### Which endpoint/mode should I use?

- **"Run this bundle"** → `--run` (execute; confirm first — real inference).
- **"Validate / dry-run / just check it"** (no cost) → `--run --endpoint validate` (or `make bundle-validate`).
- **"Resolve it / get the crate / test /v1/resolve"** → `--run --endpoint resolve`.
- **"Generate types / codegen / zod schemas / pydantic models"** → `--run --endpoint codegen --target <t>` — ask which target if the user didn't say.
- **"What inputs does this pipe need?" via the API** → `--run --endpoint build-inputs`.
- **"What does the output look like?"** → `--run --endpoint build-output` (`--output-format json` for an example-shaped view).
- **"Give me a runner script"** → `--run --endpoint build-runner`.
- **"Put it in Postman so I can click around"** → default mode (push), with the right `--endpoint`.
- **"Give me the curl"** → `--curl`. **Just checking resolution** → `--dry-run`.

## Resolution rules (mirrors `pipelex run bundle`)

- **Directory** → use `bundle.mthds` if present, else the single `*.mthds` in the dir. Multiple `.mthds` and no `bundle.mthds` is ambiguous → ask the user to pass the file directly. The sibling `inputs.json` is auto-detected. Every `*.mthds` in the directory is sent (main one first), so multi-file bundles resolve.
- **`.mthds` file** → used as-is; inputs only come from `--inputs`.
- **`pipe_code`** (run routes) comes from the bundle's `main_pipe` (override with `--pipe`); the build routes send it qualified as `pipe_ref` (`domain.pipe_code`).
- **`inputs`** is the inputs.json content copied verbatim — exactly what the API receives, same as the CLI.

## Important: file/document inputs are out of scope

We are not doing uploads. If inputs.json references a **local file** (e.g. `"url": "inputs/cv.pdf"`), the script copies it verbatim and prints a warning listing those URLs. Pass that warning on to the user: those entries must be replaced with real `https://` URLs before the request will run. Prefer demoing on a self-contained, text-input bundle.

A related limit: the API receives only the inline bundle text, not the bundle directory. Bundles that depend on Python structure classes in a `structures/` folder (rather than inline `[concept.X.structure]` blocks) won't be fully self-contained over the API — flag that if you see a `structures/` dir doing real work.

## If something's missing

- **No `POSTMAN_API_KEY`** → the script exits asking you to `source ~/.zshenv`. Do that and retry. If still unset, the user needs to add it (Postman → Settings → API keys → Generate).
- **No `main_pipe` and no `--pipe`** (execute/start/build routes) → the script exits; ask the user which pipe and pass `--pipe`.
- **`codegen` without `--target`** → the script exits listing the three targets; ask the user which consumer they're generating for.
- **`start` selected via `--run`/`--curl` and no callback URL** → the script exits. Resolve from `--callback-url`, `CALLBACK_URL` in `.env`, or ask the user (e.g. a `https://webhook.site/...` endpoint). (The Postman push never hits this — it uses the `{{callback_url}}` variable and needs no resolution.)
- **No `main_pipe`, validating/resolving** → fine, not an error: those endpoints need no pipe; validate just returns `graph_spec: null`. (On the build routes a missing `main_pipe` means `pipe_ref` cannot be defaulted — pass `--pipe`, or the server answers `422`.)

## Constants

- Collection UID: `35082494-559c5753-885c-409a-af63-7647fe28d301` (Pipelex FastAPI). Override with `--collection-uid`.
- Postman API base: `https://api.getpostman.com` (the script handles GET + PUT).
