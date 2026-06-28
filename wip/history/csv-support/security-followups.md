# CSV support — security review follow-ups (gstack /review, 2026-06-02)

The pre-landing `/review` (5 Claude specialists + Codex adversarial) confirmed the codec is well-hardened after 9 bot rounds. Three security-flavored items are captured here as deliberate decisions / deferred follow-ups rather than blockers for PR #955. The fixes the review *did* apply (BOM read, coercion-message redaction, `--save-csv` error framing) are in the PR.

## 1. Local-file read via a `url` input is the existing input model, not a CSV-specific hole — DEFERRED (platform-wide)

**Finding (security + Codex):** the CSV input hook opens a local file from an attacker-controllable `url` with no path-traversal/absolute-path confinement. `{"url": "../../some.csv"}` or `{"url": "/abs/some.csv"}` is read. Reachable from `WorkingMemoryFactory.make_from_pipeline_inputs`, the path the hosted runner API uses to build working memory from request inputs.

**Why it's not a CSV-specific blocker:** reading a local file from a `url` is the **pre-existing input model** — native `Image`/`Document` concepts already auto-populate from a local-file `url` path and load it (`image_content.py`/`document_content.py` "Auto-populate filename from url when it is a local file path", and the renderers/extractors call `load_binary` on it). The CSV hook is consistent with that model; it only extends it to flat structured concepts for `.csv`/`.xlsx`. It explicitly defers native concepts to their own handling. So "an untrusted `url` can name a local file" is a platform-wide property that pre-exists this PR, not something CSV introduces.

**The real concern (platform-wide):** *if* the hosted runner API accepts untrusted `url` inputs that reach `make_from_pipeline_inputs` without confinement, then any `url`-bearing input type (Image/Document today, CSV now) is a local-file-read primitive. CSV narrows it to `*.csv`/`*.xlsx` files specifically (the suffix is checked on the real path), but that still includes other tenants' CSVs / config CSVs on the host.

**Recommendation (own change, not this PR):** decide the runner's input-trust model and confine file-path inputs for untrusted callers at the input-resolution layer — reject absolute paths and paths escaping an allowlisted base dir — applied uniformly across **all** `url` inputs (Image/Document/CSV), not just CSV. Doing it CSV-only would be inconsistent and would also break the legitimate CLI use case (the CLI deliberately reads local files by relative/absolute path; `_inputs_path_resolver` resolves relative `url`s against the inputs-file dir). This belongs with the platform/runner input-handling, paired with the `tools/uri` scheme-classification follow-up (item A in `phase3-4-review-followups.md`).

## 2. CSV/Excel formula injection — DEFERRED by design (CT3, documented limitation)

**Finding (Codex, "block merge"):** `csv_from_list_content` writes cell values verbatim, so a value starting with `=`/`+`/`-`/`@` executes when opened in Excel/Sheets.

**Decision: this is the locked CT3 product decision, not a new bug.** plan-eng-review chose document-only on injection: do NOT auto-escape formula-leading cells (escaping mutates data and hurts fidelity), document it as a known v1 limitation, defer an opt-in `escape_formulas` flag. It is already written up in the user docs ("No formula-injection escaping") and the design. Codex flags it because it can't see the product decision. v1's primary surface is the local CLI (the user writes and opens their own CSV). The opt-in escape flag is the planned follow-up for when generated CSVs ship to third parties via the hosted runner. Not a blocker; no change in this PR.

## 3. Embedded-NUL path → raw `ValueError` escapes the codec boundary — DEFERRED (niche)

**Finding (security, sub-threshold):** a `url` whose resolved path contains an embedded NUL byte (`x\x00.csv`) makes `path.open()` raise `ValueError("embedded null byte")`, which `_read_table` doesn't catch (it wraps `OSError`/`UnicodeDecodeError`/`LookupError`/`csv.Error`). No file is opened, no traversal, no sensitive data in the message — it's an error-hygiene gap, not a security issue.

**Decision: defer.** Very niche (embedded NUL in a CSV path), and a broad `except ValueError` in `_read_table` risks masking real bugs. If we tighten it later, catch it narrowly around `path.open()` only. Low priority.
