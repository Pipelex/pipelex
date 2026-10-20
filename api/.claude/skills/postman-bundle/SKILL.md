---
name: postman-bundle
description: >-
  Turn a Pipelex MTHDS bundle into an API request against any bundle-shaped pipelex-api route — push it
  as a ready-to-run query into the live "Pipelex FastAPI" Postman collection, emit a curl command,
  execute it directly, or just preview the body. Covers the whole bundle surface: run (/v1/execute,
  /v1/start), dry-run validate (/v1/validate — no inference, no cost), crate resolution (/v1/resolve),
  and typed codegen (/v1/codegen — ts-zod, python-pydantic, python-structures). Use this whenever the user points
  at a bundle directory or a .mthds file (often with an inputs.json) and wants to run, validate,
  resolve, codegen, or otherwise test it via the API — e.g. "make a Postman query for this bundle",
  "run the fashion_moodboard bundle against the API", "validate this bundle via the API", "resolve this
  bundle to a crate", "codegen this bundle", "generate the TypeScript types for this method over the
  API", "test /v1/resolve on this bundle", "give me the curl
  for this bundle", or just "postman" said alongside a bundle path. It resolves the bundle exactly like
  `pipelex run bundle <path>` (auto-detects bundle.mthds / the single .mthds, reads main_pipe, loads the
  sibling inputs.json) and sends the method's whole tree as `files`. Trigger it even when the user does not
  name the endpoint or the word "skill".
---

# Postman Bundle

Create runnable API requests for one Pipelex MTHDS bundle and push them into the live **Pipelex FastAPI** collection (or emit curl, or run them directly), so the user can exercise any bundle-shaped endpoint against a Pipelex API server. The query resolves the bundle the same way the CLI's `pipelex run bundle <path>` does.

This is a focused, one-bundle-at-a-time tool. It is **not** the full collection sync — for diffing the whole API surface against the code, that's the separate `/update-postman` command.

## Endpoint cheat sheet

| `--endpoint` | Route | Body beside `files` | Needs a pipe? | Needs `inputs`? | Inference? |
|---|---|---|---|---|---|
| `execute` | `POST /v1/execute` | `pipe_code`, `inputs` | yes | yes | **YES — costs money** |
| `start` | `POST /v1/start` | `pipe_code`, `inputs`, `callback_urls` | yes | yes | **YES — costs money** |
| `validate` | `POST /v1/validate` | `allow_signatures`, optional `render` | no | no | no (free dry-run) |
| `resolve` | `POST /v1/resolve` | nothing | no | no | no (free) |
| `codegen` | `POST /v1/codegen` | `kind`, `target` | no | no | no (free) |

Every non-run endpoint answers with the **`/validate` verdict discipline**: a produced verdict is always a `200` discriminated on `is_valid` — the artifact on the valid arm, structured `errors[]` problem items on the invalid arm. Non-2xx is reserved for no-verdict conditions (request-shape `422`, auth `401`, server `5xx`), rendered as RFC 9457 `problem+json` with a registry `code`.

## What it produces in Postman

For the bundle the user names, it upserts requests into the collection under:

```
Bundles/
  <bundle>/            (named by the bundle's `domain`, or the filename)
    Execute (sync)             Start (async)             Validate (dry-run)
    Resolve (crate)            Codegen (types → <target>)
```

Which requests appear depends on `--endpoint`: the default `both` is `execute` + `start`; every other endpoint is pushed alone. Pushes **merge by request name** — pushing `--endpoint codegen` doesn't wipe an Execute/Start pair pushed earlier, and two codegen targets (distinct names) coexist. Requests use the collection variable `{{base_url}}` and inherit the collection's `{{auth_token}}` bearer auth (and the **Start** request's `callback_urls` is the `{{callback_url}}` variable), so the same query works against a local or hosted server by switching the Postman environment.

(The top folder used to be `Run Bundle/` — if a stale folder by that name lingers in the collection, it can be deleted.)

## The request body: the method as `files`

Every route carries the method the same way: `files`, the MTHDS standard's map of file entries. Each key is a file's tree path, its path from the method tree's root, and each value is the file's UTF-8 text, or `{"base64": "..."}` for a file whose bytes are not UTF-8, such as an image or an office template:

```json
{
  "pipe_code": "<the bundle's main_pipe>",
  "inputs": { "...": "inputs.json copied verbatim" },
  "files": {
    "bundle.mthds": "domain = \"greeting\"\nmain_pipe = \"greet\"\n...",
    "templates/card.html": "<p>Hello, {{ text }}</p>\n",
    "assets/logo.png": { "base64": "iVBORw0KGgo..." }
  }
}
```

`pipe_code` and `inputs` ride execute/start only, `allow_signatures` and the optional `render` ride validate, and `kind`/`target` ride codegen; `resolve` sends `files` alone. The **start** body additionally carries `callback_urls` (see [Callback URLs](#callback-urls-the-async-start-endpoint)). `files` comes last in every body, so the fields you edit in Postman stay on top.

What travels is **every file of the method's tree**, listed by the `mthds` package's own lister, so it is judged by the same membership rule the runner and every MTHDS client apply (the standard's `method-tree.md`):

- **The root** is the nearest directory at or above the bundle holding `METHODS.toml`, else the directory you point at. A `.mthds` file named alone with no `METHODS.toml` above it travels as the one-file tree of that file, nothing beside it.
- **What stays out**: every path segment starting with a dot (`.git/`, `.venv/`, `.env`, `.mthds/`), `__pycache__` and `node_modules`, virtual environments, nested repositories and nested packages, the tree's own `.gitignore`d files and the manifest's `[package] exclude` patterns, and whatever else the installed `mthds` keeps out, such as a run's `inputs.json` once it applies the standard's rule for it.
- **Never by hash.** The standard's third entry form, `{"sha256", "size"}`, names bytes the runner already holds in its blob store, which only an upload (`POST /v1/blobs/missing`, then `PUT /v1/blobs/{sha256}`) puts there. A Postman query or a curl command never uploads, so every file travels inline.
- **No retired fields.** The skill never sends `mthds_contents`, `mthds_sources`, `bundle_b64` or `resources`.

The listing stops at the runner's own limits on a tree a request sends (the `MAX_METHOD_TREE_*` limits of `pipelex_api.limits`), so pointing the skill at a large directory by mistake fails in moments. The script also refuses a main bundle the membership rule keeps out of the tree, such as a `.gitignore`d one, since the `pipe_code` read from it would name a pipe the runner never receives.

## Validate = the API's dry-run

`POST /v1/validate` is the API's dry-run: it parses, loads, and dry-runs every pipe with mock inputs and **zero inference** (no LLM calls, no cost), then returns the validated bundle blueprint, a `graph_spec`, and per-pipe input/output JSON-Schema `pipe_io_contracts`. It confirms the whole pipeline wires up without ever running it — the safe, free counterpart to `execute`/`start`. Reach for it to "just check" or "dry-run" a bundle.

- **`main_pipe` is optional for `/validate`.** A bundle with no `main_pipe` still validates (200, `is_valid: true`) — you just get `graph_spec: null`. `--pipe` is ignored.
- **`allow_signatures`** (`--allow-signatures`) tolerates unimplemented pipe signatures instead of rejecting the bundle (each dry-runs trivially by minting a mock). Useful for in-progress bundles. It parameterizes the **dry-run sweep**, so it rides `validate` only — the crate routes run no sweep and do not accept it. Default strict.
- **`render`** (`--render markdown`) opts into a server-rendered Markdown view of the verdict, riding the 200 on both arms as `rendered_markdown`. This is what a **skill**-driven validate sends; a **hook** omits it and reads the structured `is_valid`. The structured fields stay the contract; the Markdown is the view.

## Resolve & Codegen (the crate routes)

**`POST /v1/resolve`** resolves the library closure into its **normalized crate** — fully qualified refs, flattened refinement, materialized natives, fingerprint set. It runs no dry-run sweep (runnability is `/validate`'s vocabulary). The valid arm carries the canonical JSON crate — the same bytes `pipelex resolve --format json` prints, so a fingerprint computed from either surface agrees.

**`POST /v1/codegen`** resolves the closure the same way, then projects the crate through two explicit axes: `kind` (only `types` is served — an inputs template is projected client-side from the input form `POST /v1/pipe-io` serves) × `target`:

- `ts-zod` — zod schemas + inferred TypeScript types
- `python-pydantic` — self-contained pydantic BaseModels
- `python-structures` — Pipelex runtime `StructuredContent` classes (a Pipelex extension)

The valid arm carries the **stamped** artifact set plus its `codegen.lock`: a client that writes them verbatim reproduces a local `pipelex codegen types` run **byte-for-byte** and passes the offline `pipelex codegen check`. There is deliberately no server-side check route (the drift check is offline by design). An unknown `kind`/`target`, or a `pipe_ref` on the concept-set-wide `types`, is a request-shape `422`.

`--target` is **required** for codegen — there is no default; ask the user which consumer they're generating for if unclear. The request also accepts a `method_ref` instead of `files` (an address-form reference is fetched and resolved; the registry form is a `422 request.unsupported`) — this skill always sends `files`.

## Callback URLs (the async `start` endpoint)

`/v1/start` is fire-and-forget: it returns a `run_id` immediately and POSTs the finished result to a webhook later, so a `start` request **must** carry `callback_urls`.

**Postman push (default mode) always uses the `{{callback_url}}` collection variable** — never a baked-in URL. The pushed body is `"callback_urls": ["{{callback_url}}"]`, so the callback is switchable in the Postman environment right alongside `base_url` and `auth_token` (local vs hosted). Nothing to resolve — just tell the user to set `callback_url` in their Postman environment (a `https://webhook.site/...` endpoint is the easy way to watch the result land).

**`--run` / `--curl` (a real HTTP call, or a preview of one) need a concrete URL.** Resolution order there:

1. **`--callback-url <url>`** (repeatable — the field is a JSON list; a single URL is the common case).
2. **`CALLBACK_URL`** in the environment or the repo `.env`. `make` exports `.env`; the script also reads `.env` directly when invoked outside `make`.
3. **Ask the user.** If neither is set, the script stops with a clear error — ask for a callback URL and re-run with `--callback-url`.

This only affects `start` — no other endpoint takes `callback_urls`. The API's SSRF guard rejects loopback/private/metadata hosts, so a `localhost` callback won't validate — use a public `https://` URL.

## How to run it

Every command on this page runs from `api/`, the server's directory in the pipelex repository: `cd api` first, or prefix the make targets with `-C api` from the repository root (`make -C api bundle-run …`), and give `BUNDLE` and the script's paths relative to `api/`. The script lists the method's tree with the `mthds` package and reads the runner's limits from `pipelex_api`, so it runs with the server's own environment, `api/.venv`, never a bare `python3`. The make targets are the convenient wrapper: they install that environment, then run the script with it.

```bash
make bundle-run      BUNDLE=<dir|.mthds>                 # POST to a running API, print the response
make bundle-validate BUNDLE=<dir|.mthds>                 # dry-run validate via /v1/validate (free)
make bundle-resolve  BUNDLE=<dir|.mthds>                 # resolve to the normalized crate (free)
make bundle-codegen  BUNDLE=<dir|.mthds> TARGET=ts-zod   # project typed artifacts + lock (free)
make bundle-curl     BUNDLE=<dir|.mthds>                 # emit a ready-to-run curl
make bundle-postman  BUNDLE=<dir|.mthds>                 # push request(s) into the Postman collection
make bundle-dry      BUNDLE=<dir|.mthds>                 # print the request body only
# optional: ENDPOINT=execute|start|validate|resolve|codegen|both
#           PIPE=<code>  INPUTS=<path>  NAME=<folder>  ALLOW_SIGNATURES=1  TARGET=<codegen target>
#           CALLBACK_URL=<url>  BASE_URL=<url>  TOKEN=<bearer>  ARGS=<extra>
```

`bundle-validate` / `bundle-resolve` / `bundle-codegen` hardcode `--run` with their endpoint (they're free and safe to run live).

Under the hood it's one script that resolves the bundle once and sends the request to one of four sinks. `<bundle-path>` is a bundle **directory** (preferred) or a single `.mthds` file. Call the script directly for a path outside the repo or finer control, with the server's environment (`make install` creates it when it is missing):

**Push into the Postman collection** (default). Source the env first so the Postman key is present (it lives in `~/.zshenv`):

```bash
source ~/.zshenv 2>/dev/null
.venv/bin/python .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> [--endpoint <ep>] [--target <t>]
```

After a successful push, tell the user it's in Postman (it auto-syncs), and that they should set `base_url` and `auth_token` in their Postman environment, then Send.

**Run it yourself from Claude Code** — POSTs the exact same body to a running API and prints the response:

```bash
.venv/bin/python .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint <ep>
# defaults to http://127.0.0.1:8081 and no auth (AUTH_MODE=none). Override:
#   --base-url https://api.pipelex.com   --token <bearer>
```

The API must be up — start it locally with `make run` first. **Heads-up: only `execute`/`start` trigger real inference (cost + latency)** — confirm the user wants a live run for those. Every other endpoint is free and safe to fire without confirmation:

```bash
.venv/bin/python .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint validate
.venv/bin/python .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint resolve
.venv/bin/python .claude/skills/postman-bundle/scripts/build_postman_query.py <bundle-path> --run --endpoint codegen --target python-pydantic
```

**Emit a curl command** (`--curl`) — writes the body to a temp file and prints a `curl --data @file`, so the files' contents never need shell escaping. **Preview only** (`--dry-run`) — print the request body, touch nothing. Every mode prints the tree's root and the files it sends first, marking those that travel in Base64.

Useful options (apply across modes):

| Option | When to use |
|---|---|
| `--endpoint <ep>` | Pick the endpoint (see cheat sheet). Default `both` (= execute + start) for Postman/curl; `--run both` runs `execute`. |
| `--target <t>` | (codegen only, **required**) `ts-zod`, `python-pydantic`, or `python-structures`. |
| `--allow-signatures` | (validate only) Tolerate unimplemented pipe signatures. Default strict. |
| `--render <fmt>` | (validate only) Opt-in server-side view, e.g. `--render markdown` → response carries `rendered_markdown` (what a skill-driven validate sends). Omit for the lean structured body a hook reads. Repeatable. |
| `--inputs <path>` | Inputs JSON lives elsewhere, or you point at a `.mthds` file directly (file mode does not auto-detect inputs). execute/start only. |
| `--pipe <pipe_code>` | The bundle has no `main_pipe`, or you want a different pipe. Used by execute/start (as `pipe_code`); ignored by validate/resolve/codegen. |
| `--callback-url <url>` | (start only) Webhook the async result is POSTed to. Repeatable. Falls back to `CALLBACK_URL` in env/`.env`. |
| `--base-url` / `--token` | Target server + bearer for `--run`/`--curl`. |
| `--name <folder>` | Override the per-bundle Postman subfolder name. |

### Which endpoint/mode should I use?

- **"Run this bundle"** → `--run` (execute; confirm first — real inference).
- **"Validate / dry-run / just check it"** (no cost) → `--run --endpoint validate` (or `make bundle-validate`).
- **"Resolve it / get the crate / test /v1/resolve"** → `--run --endpoint resolve`.
- **"Generate types / codegen / zod schemas / pydantic models"** → `--run --endpoint codegen --target <t>` — ask which target if the user didn't say.
- **"Put it in Postman so I can click around"** → default mode (push), with the right `--endpoint`.
- **"Give me the curl"** → `--curl`. **Just checking resolution** → `--dry-run`.

## Resolution rules (mirrors `pipelex run bundle`)

- **Directory** → the main bundle is `bundle.mthds` if present, else the single `*.mthds` in the dir. Multiple `.mthds` and no `bundle.mthds` is ambiguous → ask the user to pass the file directly. The sibling `inputs.json` is auto-detected. The directory's whole method tree is sent as `files`, its bundles in subdirectories included, so multi-file methods resolve.
- **`.mthds` file** → the main bundle is that file, and the tree it belongs to is sent: the package's tree when a `METHODS.toml` sits at or above its directory, else that one file. Inputs only come from `--inputs`.
- **`pipe_code`** (run routes) comes from the main bundle's `main_pipe` (override with `--pipe`).
- **`inputs`** is the inputs.json content copied verbatim — exactly what the API receives, same as the CLI.

## Important: file/document inputs are out of scope

We are not doing uploads. If inputs.json references a **local file** (e.g. `"url": "inputs/cv.pdf"`), the script copies it verbatim and prints a warning listing those URLs. Pass that warning on to the user: those entries must be replaced with real `https://` URLs before the request will run. Prefer demoing on a self-contained, text-input bundle.

The method's own files are a different matter: a template, an image or a module the steps read travels in `files` with the bundles. Python is the one limit: a tree holding a `.py` file runs only on a sandbox-hosted runner (any other answers a `501`), and a Python structure class is refused on every runner, so a method whose concepts rely on a `structures/` folder of Python classes, rather than inline `[concept.X.structure]` blocks, will not run over the API — flag that if you see a `structures/` dir doing real work.

## If something's missing

- **No `POSTMAN_API_KEY`** → the script exits asking you to `source ~/.zshenv`. Do that and retry. If still unset, the user needs to add it (Postman → Settings → API keys → Generate).
- **No `main_pipe` and no `--pipe`** (execute/start) → the script exits; ask the user which pipe and pass `--pipe`.
- **`codegen` without `--target`** → the script exits listing the three targets; ask the user which consumer they're generating for.
- **`start` selected via `--run`/`--curl` and no callback URL** → the script exits. Resolve from `--callback-url`, `CALLBACK_URL` in `.env`, or ask the user (e.g. a `https://webhook.site/...` endpoint). (The Postman push never hits this — it uses the `{{callback_url}}` variable and needs no resolution.)
- **No `main_pipe`, validating/resolving** → fine, not an error: those endpoints need no pipe; validate just returns `graph_spec: null`.
- **The tree cannot be listed** (a symbolic link or a name the standard refuses inside it, a malformed `METHODS.toml`, a tree past the runner's limits) or **the main bundle is outside its own tree** (`.gitignore`d, say) → the script exits naming the cause; fix the method's directory, or point at the method's own folder rather than a directory above it.
- **`ModuleNotFoundError: mthds` or `pipelex_api`** → the script ran with the wrong interpreter: use `.venv/bin/python` from `api/` (`make install` creates it) or a `make bundle-*` target.

## Constants

- Collection UID: `35082494-559c5753-885c-409a-af63-7647fe28d301` (Pipelex FastAPI). Override with `--collection-uid`.
- Postman API base: `https://api.getpostman.com` (the script handles GET + PUT).
