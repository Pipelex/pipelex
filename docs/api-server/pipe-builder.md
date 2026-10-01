# Pipe Builder

Generate input templates, output representations, and Python runner code for a pipe of an MTHDS library closure.

All three build endpoints speak the same verdict discipline as [`POST /v1/validate`](pipe-validate.md): a **produced verdict is always a `200`** discriminated on the body's `is_valid` field. The valid arm carries the built artifact; the invalid arm carries the structured `validation_errors[]` built by pipelex's one shared error builder. Non-2xx is reserved for *no verdict could be produced* — request-shape `422`, auth `401`/`403`, server `5xx` — rendered as RFC 7807 `application/problem+json` (see [Error Responses](error-responses.md)).

## The shared request envelope

All three take the same **closure selector** as [`POST /v1/resolve` and `POST /v1/codegen`](codegen.md) — inline `files[]` **XOR** a `method_ref` — plus a **pipe selector**:

- `files` (list, required unless `method_ref`): the inline MTHDS bundles forming the closure. Each item is `{ "content": "<mthds text>", "source": "<optional logical path>" }`. The optional `source` is threaded onto the blueprint, so diagnostics point at the owning file.
- `method_ref` (string): a reference to a published method. The **address form** — `github.com/<owner>/<repo>` plus an optional package selector and `@<tag>` — is resolved server-side through the same fetch path as a [`method_ref` run](pipe-run.md#running-a-method-by-address-method_ref): the package's `.mthds` files feed the closure (only `.mthds` data travels — the package's Python never loads here), and the package manifest's `main_pipe` becomes the default pipe selector. The **registry form** (any non-address reference) answers `501` (`MethodRefNotSupported`) until method-registry resolution lands.
- `pipe_ref` (string, **optional**): the qualified pipe ref `domain.pipe_code` to project — the same selector as `pipelex codegen inputs --pipe`. Omitted, it defaults with the same precedence as a run by address: on a `method_ref` request, to the fetched package manifest's `main_pipe` (the package author's declared entry pipe); otherwise to the closure's own declared `main_pipe`. A closure that declares **no** `main_pipe`, or **several** across domains, cannot be defaulted from its declarations, so when no manifest `main_pipe` settles it an omitted `pipe_ref` is a `422` there. Inline `files[]` carry no manifest, so for them the default is always the closure's declaration. Every selection refusal is an input `422` whose `error_type` is the pipelex entry-lookup class that names the failure, not the `ValidationError` of a malformed request: `EntryPipeNotFoundError` for a `pipe_ref` that names no pipe, a manifest `main_pipe` the closure does not declare, or an omitted `pipe_ref` over a closure declaring no `main_pipe`; `EntryPipeAmbiguousError` for a bare code, whether the request or the manifest spelled it, that matches pipes in several domains, or an omitted `pipe_ref` over a closure declaring several `main_pipe`s. An ambiguity's `detail` names the qualified refs to choose from. An unknown or ambiguous `pipe_ref` answers the `error_type` the run routes answer for the same `pipe_code`; the two omitted-`pipe_ref` refusals follow the pipe-selector design, since a run over such a closure has no matching refusal today.

Every valid arm echoes both `pipe_ref` (the ref actually projected) and `requested_pipe_ref` (the ref as submitted — **absent** when it was omitted and defaulted), so a caller can always see which pipe it got. The echoed `pipe_ref` is **always qualified**, read back off the resolved pipe: a bare code still resolves (the engine's lookup falls back across domains), but you are told `smoke.echo`, not the `echo` you sent.

## Static projections vs. the runner

`/build/inputs` and `/build/output` are **static**: they resolve the closure to its normalized crate and read the requested pipe's **declared** IO. There is no dry-run sweep, and therefore no `allow_signatures` flag (it only ever parameterized that sweep). A valid verdict from them says the closure is structurally sound and the projection matches what the pipe *declares* — it is **not** a promise the pipe runs. Runnability is [`/validate`](pipe-validate.md)'s vocabulary; ask it.

`/build/runner` is the exception. A runner script *is* a promise the pipe can run, so it keeps the dry-run sweep and keeps `allow_signatures`.

## Build Inputs

Generate an example inputs template for a pipe — the same projection `pipelex codegen inputs` writes, on both of its axes.

**Endpoint:** `POST /v1/build/inputs`

**Request Body:**

```json
{
  "files": [
    { "content": "domain = \"cv_matching\"\nmain_pipe = \"analyze_cv_job_match\"\n\n[pipe.analyze_cv_job_match]\ntype = \"PipeLLM\"\ndescription = \"Analyze CV against job offer\"\ninputs = { cv_text = \"native.Text\", job_offer = \"native.Text\" }\noutput = \"MatchAnalysis\"", "source": "cv_matching.mthds" }
  ],
  "pipe_ref": "cv_matching.analyze_cv_job_match"
}
```

**Request Fields:** the shared envelope above, plus:

- `format` (string, optional): `"json"` (default) or `"toml"`.
- `explicit` (boolean, optional, default `false`): when `true`, emit the ceremonial `{concept, content}` envelope for every input. The default is the *light*, signature-driven shape — a bare string for a Text-refining input, a bare number for a Number-refining one, and so on — which is what smart inputs accepts.

**The template rides the field its `format` names.** JSON is a parsed object in `inputs`; TOML is raw text in `inputs_toml`. TOML cannot ride as a parsed object without losing the concept comments and key order that are the reason to ask for it, and the JSON case must stay a real object because that is what clients feed straight into a run. The field the format did not select is **omitted from the body entirely**.

**Response (valid verdict, default light JSON):**

```json
{
  "is_valid": true,
  "pipe_ref": "cv_matching.analyze_cv_job_match",
  "requested_pipe_ref": "cv_matching.analyze_cv_job_match",
  "format": "json",
  "explicit": false,
  "inputs": {
    "cv_text": "text_value",
    "job_offer": "text_value"
  },
  "message": "Inputs template generated successfully"
}
```

With `"explicit": true`, each value becomes its `{ "concept": "native.Text", "content": { "text": "text_value" } }` envelope instead. With `"format": "toml"`, the body carries `inputs_toml` (a string) in place of `inputs`.

A pipe that declares **no inputs** is a *valid* verdict, not an error: the template is simply empty (`{}` / `""`) and `message` says so — mirroring the CLI, which exits 0 on it.

**Response (invalid verdict):** `200` with `is_valid: false` and `validation_errors[]` — the same invalid arm every build endpoint returns:

```json
{
  "is_valid": false,
  "validation_errors": [
    { "category": "blueprint_validation", "message": "...", "source": "cv_matching.mthds" }
  ],
  "message": "..."
}
```

An item may also carry a `suggested_fix` — a structured, deterministic repair the runtime derived for that error. See [Error Responses → Suggested fixes](error-responses.md#suggested-fixes).

---

## Build Output

Generate the output representation for a pipe in one of three formats.

**Endpoint:** `POST /v1/build/output`

**Request Body:**

```json
{
  "files": [{ "content": "...your MTHDS content..." }],
  "pipe_ref": "cv_matching.analyze_cv_job_match",
  "format": "schema"
}
```

**Request Fields:** the shared envelope above, plus:

- `format` (string, optional): `"schema"` (default), `"json"`, or `"python"`. **Must be lowercase.**

**Format Options:**

- `schema` — JSON Schema representation of the output concept → parsed object in `output`
- `json` — Example JSON instance of the output → parsed object in `output`
- `python` — Python source defining the output class → raw text in `output_python`

As with `/build/inputs`, the representation rides the field its `format` names, and the other is omitted.

**Response (valid verdict, schema format):**

```json
{
  "is_valid": true,
  "pipe_ref": "cv_matching.analyze_cv_job_match",
  "requested_pipe_ref": "cv_matching.analyze_cv_job_match",
  "format": "schema",
  "output": {
    "concept": "MatchAnalysis",
    "content": {
      "type": "object",
      "properties": {
        "score": { "title": "Score", "type": "integer", "description": "Match score 0-100" }
      },
      "required": ["score"]
    }
  },
  "message": "Output representation generated successfully"
}
```

One no-verdict special case: a pipe whose output is `native.Anything` and whose concrete options cannot be determined has no representation to render — a request-shape `422`, since that is a fact about the requested pipe, not about the closure.

The invalid verdict is the shared `is_valid: false` arm shown under Build Inputs.

---

## Build Runner

Generate a Python runner script for executing a pipe. The script's imports, example inputs, and output cast are spelled with the **emitted** class names of the typed-structures projection, and the response carries that projection alongside the script — the same stamped `structures.py` + `codegen.lock` a local `pipelex build runner` scaffolds (see [Resolve & Codegen](codegen.md) for the stamp/lock trust chain).

**Endpoint:** `POST /v1/build/runner`

**Request Body:**

```json
{
  "files": [{ "content": "...your MTHDS content..." }],
  "pipe_ref": "cv_matching.analyze_cv_job_match"
}
```

**Request Fields:** the shared envelope above, plus:

- `allow_signatures` (boolean, optional): tolerate unimplemented pipe signatures in the dry-run sweep (default `false`). This is the only build route that takes it — the only one that still sweeps.
- `analytics_groups` (object | null, optional): the groups the caller belongs to, with the same rules and the same 422 `InvalidAnalyticsGroups` as [on `/validate`](pipe-validate.md#who-the-validation-is-done-for). The sweep is done for the authenticated user and these groups, so its telemetry is attributed to them.

The sweep is scoped to the requested pipe, so unrelated broken siblings do not block a good pipe. When `pipe_ref` is omitted the scope is not settled before the closure loads, so the **whole closure** is swept and the pipe then defaults as described in the shared envelope above — the fetched manifest's `main_pipe` on a `method_ref` request, else the closure's own — a stricter verdict, and the honest one for a caller who did not say which pipe they meant.

**Response (valid verdict):**

```json
{
  "is_valid": true,
  "pipe_ref": "cv_matching.analyze_cv_job_match",
  "requested_pipe_ref": "cv_matching.analyze_cv_job_match",
  "python_code": "import sys\nfrom pathlib import Path\n...",
  "structures": {
    "directory": "structures",
    "artifacts": [
      { "path": "structures.py", "content": "# >>> pipelex-codegen-stamp >>>\n..." }
    ],
    "lock": "# codegen.lock — generated artifact set (Pipelex codegen). Do not edit by hand.\n...",
    "lock_filename": "codegen.lock"
  },
  "message": "Runner code generated successfully"
}
```

To materialize a runnable tree, write `python_code` as the runner script and each `structures.artifacts[]` entry (plus `structures.lock` as `structures.lock_filename`) into the `structures.directory` beside it — the script imports from there (`from structures.structures import ...`).

The invalid verdict — including a failed dry-run of the requested pipe — is the shared `is_valid: false` arm shown under Build Inputs. One no-verdict special case: a requested pipe whose cross-package dependencies are absent from the request (recorded SKIPPED by the sweep) is a request-shape `422`, since no runner can be honestly generated without its dependency closure.
