# Resolve & Codegen

Resolve a library closure into its **normalized library crate**, and project that crate into typed artifacts (zod schemas, pydantic models, runtime structures) — over HTTP, with the same engine and the same trust chain as the local `pipelex resolve` / `pipelex codegen` commands.

Both are **Pipelex API extensions**, not MTHDS Protocol routes: they are not tagged `x-mthds-protocol` in the [OpenAPI artifact](openapi/pipelex-api.openapi.yaml), and an MTHDS runner is not required to serve them. The *crate* is a different matter — its shape is the standard's [Library Crate Format](https://mthds.ai), so the wire fields are brand-neutral and any MTHDS tool can read one. What is ours is the HTTP surface that produces it, and the type projection on top (the standard specifies none).

Both endpoints speak the [`POST /v1/validate`](pipe-validate.md) verdict discipline: a **produced verdict is always a `200`** discriminated on `is_valid`; the invalid arm carries the structured `validation_errors[]` from pipelex's one shared builder — each item optionally carrying a [`suggested_fix`](error-responses.md#suggested-fixes). Non-2xx is reserved for *no verdict could be produced*: request-shape errors (an unknown projection `kind`/`target`, a malformed closure selector) are `422` RFC 7807 `application/problem+json`, a registry-form `method_ref` is `501`, an address-form `method_ref` that fails to resolve maps per the [`method_ref` error table](pipe-run.md#running-a-method-by-address-method_ref), auth is `401`/`403`, server faults are `5xx`.

## Selecting the closure

Both endpoints accept the same closure selector — exactly one of:

- `files` (list, content-passing): inline MTHDS bundles, each `{ "content": "...", "source": "optional/logical/path.mthds" }`. `source` threads onto diagnostics and the crate's `source_map`.
- `method_ref` (string): a reference to a published method. The **address form** — `github.com/<owner>/<repo>` plus an optional package selector and `@<tag>` — is resolved server-side through the same fetch path as a [`method_ref` run](pipe-run.md#running-a-method-by-address-method_ref): the package's `.mthds` files feed the closure, each with its real relative path as `source` (so diagnostics and the crate's `source_map` carry true per-file labels). Only `.mthds` data travels on these routes — the package's Python (if any) never loads here. The **registry form** (any non-address reference) stays reserved: the server answers **`501`** (`MethodRefNotSupported`) until method-registry resolution lands.

Providing neither or both is a request-shape `422`.

## Resolve

**Endpoint:** `POST /v1/resolve`

Resolution is a first-class language operation alongside validation: the closure is merged, every ref fully qualified, refinement flattened, natives materialized, and the crate's canonical `fingerprint` computed. Resolution is **static** — it runs no dry-run sweep (runnability is `/validate`'s vocabulary), and the crate is emitted only from a library that loaded and validated.

**Request Body:**

```json
{
  "files": [
    { "content": "...bundle one...", "source": "main.mthds" },
    { "content": "...bundle two...", "source": "steps.mthds" }
  ]
}
```

**Response (valid verdict):**

```json
{
  "is_valid": true,
  "crate": {
    "mthds_version": "…",
    "concepts": { "…": {} },
    "pipes": { "…": {} },
    "domains": { "…": {} },
    "source_map": { "…": "main.mthds" },
    "fingerprint": "…"
  },
  "message": "MTHDS library resolved successfully"
}
```

`crate` is the canonical JSON encoding of the normalized crate — the same bytes `pipelex resolve --format json` prints, so fingerprints computed from either surface agree.

**Response (invalid verdict):** `200` with `is_valid: false` and `validation_errors[]` (no crate exists).

## Codegen

**Endpoint:** `POST /v1/codegen`

Resolves the closure exactly like `/resolve`, then projects the crate through the two explicit axes:

- `kind` (string, required): what to project. Served: `types` (the crate's concept set as typed models). Membership follows the **trust chain** — a kind is served here exactly when its artifacts are stamped and locked, which is the promise the valid arm makes by carrying a `lock`. Input templates are user-editable scaffolds, never stamped or locked, so they cannot make that promise: they ride [`POST /v1/build/inputs`](pipe-builder.md) instead and `inputs` is deliberately **not** a kind here.
- `target` (string, required): for whom. `ts-zod` (zod schemas + inferred types), `python-pydantic` (self-contained pydantic models), or `python-structures` (runtime `StructuredContent` classes, for a Pipelex host).
- `pipe_ref` (string, optional): pipe selector for future per-pipe kinds — not accepted for `types` (request-shape `422`).

An unknown `kind` or `target` is a request-shape `422` problem+json, never a `200` with an error body.

**Request Body:**

```json
{
  "files": [{ "content": "...bundle..." }],
  "kind": "types",
  "target": "ts-zod"
}
```

**Response (valid verdict):**

```json
{
  "is_valid": true,
  "kind": "types",
  "target": "ts-zod",
  "crate_fingerprint": "…",
  "engine_version": "…",
  "artifacts": [
    { "path": "types.ts", "content": "// >>> pipelex-codegen-stamp >>>\n…" }
  ],
  "lock": "# codegen.lock — generated artifact set (Pipelex codegen). Do not edit by hand.\n…",
  "lock_filename": "codegen.lock",
  "message": "Codegen artifacts generated successfully"
}
```

### The trust chain over HTTP

Every artifact ships **stamped** (source-crate fingerprint, engine version, projection, content hash) and the response carries the matching `codegen.lock`. A client that writes each `artifacts[]` entry and the `lock` **verbatim** reproduces a local `pipelex codegen types` run byte-for-byte — so the offline `pipelex codegen check` passes on the written tree exactly as it would on locally generated files.

There is deliberately **no** server-side check route: the drift check is pure hashing over local files, offline by design.
