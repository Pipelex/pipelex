# Resolve & Codegen

Resolve a library closure into its **normalized library crate**, and project that crate into typed artifacts (zod schemas, pydantic models, runtime structures) — over HTTP, with the same engine and the same trust chain as the local `pipelex resolve` / `pipelex codegen` commands.

Both are **Pipelex API extensions**, not MTHDS Protocol routes: they are not tagged `x-mthds-protocol` in the [OpenAPI artifact](openapi/pipelex-api.openapi.yaml), and an MTHDS runner is not required to serve them. The *crate* is a different matter — its shape is the standard's [Library Crate Format](https://mthds.ai), so the wire fields are brand-neutral and any MTHDS tool can read one. What is ours is the HTTP surface that produces it, and the type projection on top (the standard specifies none).

Both endpoints speak the [`POST /v1/validate`](pipe-validate.md) verdict discipline: a **produced verdict is always a `200`** discriminated on `is_valid`; the invalid arm carries the structured `validation_errors[]` from pipelex's one shared builder — each item optionally carrying a [`suggested_fix`](error-responses.md#suggested-fixes). Non-2xx is reserved for *no verdict could be produced*: request-shape errors (an unknown projection `kind`/`target`, a malformed method selector) and a method tree that cannot be read are `422` RFC 7807 `application/problem+json`, the custom-Python policy is a `403`, a registry-form `method_ref` is `501`, an address-form `method_ref` that fails to resolve maps per the [`method_ref` error table](pipe-run.md#running-a-method-by-address-method_ref), auth is `401`/`403`, server faults are `5xx`.

## Selecting the method

Both endpoints take the method the way [`POST /v1/validate`](pipe-validate.md#validating-a-method-tree) and the [run routes](pipe-run.md#sending-a-method-as-a-tree) take it, as a method tree, read by the same machinery, so a tree one route accepts, refuses or resolves, the others accept, refuse or resolve the same way. The request names it with exactly one of:

- `files` (object): the method as the MTHDS protocol's map of file entries, each key a tree path and each value the file's text, `{"base64": "…"}` or `{"sha256": "…", "size": n}` naming bytes this runner already holds in its [blob store](pipe-run.md#sending-files-by-hash). The tree is written whole and loaded as the caller's library directory: every `.mthds` bundle is named by its tree path, which threads onto diagnostics and the crate's `source_map`, and every other file is one a step may read, such as a `PipeDocGen` template beside its bundle.
- `method_ref` (string): a reference to a published method. The **address form**, `github.com/<owner>/<repo>` plus an optional package selector and `@<tag>`, is resolved server-side through the same fetch path as a [`method_ref` run](pipe-run.md#running-a-method-by-address-method_ref): the package's whole tree is read from the commit and loaded as a tree sent in `files` is, and the packages it ships under its own `.mthds/methods/<name>/` are loaded beside it, so a call into one resolves. The **registry form** (any non-address reference) stays reserved: the server answers **`501`** (`MethodRefNotSupported`) until method-registry resolution lands.

Providing neither or both is a request-shape `422`. Beside `files`, the request may also carry:

- `dependencies` (object): the method packages the method calls by address, each a map of file entries keyed by its address, as on a [run](pipe-run.md#sending-the-method-packages-the-method-calls). They are loaded beside the method, never merged into it, so a cross-package call resolves without the server fetching or holding a copy. `dependencies` without `files` is a request-shape `422`.
- `resources` (object): files the method's steps read, such as a `PipeDocGen` step's `template_file`, keyed by the path from the tree's root, each in standard base64, joining the tree with the rules and refusals of [`/v1/validate`](pipe-validate.md#sending-the-files-the-steps-read-resources). A step that names a template file the tree does not hold cannot be built, so the method is invalid. `resources` beside a `method_ref` is a request-shape `422`: a published method's files are its package's own.
- `read_scope` (string): **Pipelex-API extension.** The scope the request reads the method under, as on `/v1/validate`: a hash entry of `files` resolves in that scope's blob store, else in the caller's own id's, and only a request carrying a `read_scope` records the tree it read in the blob store.

**The tree's refusals produce no verdict**, exactly as on `/v1/validate`: a key or entry the tree's rule refuses is a `422 InvalidMethodFiles` with its `tree_refusal` member, a hash the runner does not hold a `422 MissingBlobs`, a tree past its limits a `422 MethodTreeTooLarge`, and a tree holding no `.mthds` bundle of its own a `422 InvalidBundle`. A `files` member that is not a map, such as a list, is an `InvalidMethodFiles` too.

**Python follows the run routes' policy.** Loading a method's library on a deployment that is not sandbox-hosted could import its Python into the server's process, so there a tree, sent or fetched, that holds any `.py` file is refused with a `403 CustomCodeRequiresSandbox` before anything is written. On a sandbox-hosted deployment, a tree whose Python declares a structure class is refused with a `403 MethodStructuresRefusedError`, as on a [run](pipe-run.md#sending-a-method-as-a-tree).

## Resolve

**Endpoint:** `POST /v1/resolve`

Resolution is a first-class language operation alongside validation: the closure is merged, every ref fully qualified, refinement flattened, natives materialized, and the crate's canonical `fingerprint` computed. Resolution is **static** — it runs no dry-run sweep (runnability is `/validate`'s vocabulary), and the crate is emitted only from a library that loaded and validated.

**Request Body:**

```json
{
  "files": {
    "main.mthds": "...bundle one...",
    "steps/extract.mthds": "...bundle two...",
    "templates/invoice.docx": { "sha256": "3e9b68b71cc667168399f0bccfb64b2d16314cdc0ed78fac4819aba0dda121a0", "size": 18342 }
  }
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

- `kind` (string, required): what to project. Served: `types` (the crate's concept set as typed models). Membership follows the **trust chain** — a kind is served here exactly when its artifacts are stamped and locked, which is the promise the valid arm makes by carrying a `lock`. Input templates are user-editable scaffolds, never stamped or locked, so they cannot make that promise: a client projects one from the input form [`POST /v1/pipe-io`](pipe-io.md) serves, and `inputs` is deliberately **not** a kind here.
- `target` (string, required): for whom. `ts-zod` (zod schemas + inferred types), `python-pydantic` (self-contained pydantic models), or `python-structures` (runtime `StructuredContent` classes, for a Pipelex host).
- `pipe_ref` (string, optional): pipe selector for future per-pipe kinds — not accepted for `types` (request-shape `422`).

An unknown `kind` or `target` is a request-shape `422` problem+json, never a `200` with an error body.

**Request Body:**

```json
{
  "files": { "main.mthds": "...bundle..." },
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
