# CSV support — Phase 3+4 code-review follow-ups

Deferred items from the xhigh code review of the Phase 3 (input hook) + Phase 4 (`--save-csv`) work (2026-06-02). The two confirmed bugs (#1 query-string remote-rejection, #2 `ConceptValueError` wrap) and the cheap UX guards (#7 empty `--save-csv`, #8 parent-dir creation) were **fixed in that session** — see `stuff_factory._try_make_csv_list_stuff` and `_run_core._execute_run`. This file captures the items deliberately **not** patched: design-tradeoff / right-depth calls that deserve a decision rather than a reflexive fix.

## Deferred — design / altitude

### A. `resolve_uri` does not classify non-file remote schemes (`s3://`, `gs://`, …)

`resolve_uri` only special-cases `data:`, `pipelex-storage://`, `file://`, and `http(s)://`; **every other scheme falls through to `ResolvedLocalPath(path=<uri>)`** (`pipelex/tools/uri/uri_resolver.py` final `return`). So `s3://bucket/x.csv` is reported as a *local path* whose `.path` still contains `s3://...`.

The CSV input hook works around this with a string heuristic — `not isinstance(resolved, ResolvedLocalPath) or "://" in resolved.path` — to reject those as remote. That works, but:

- It encodes a fragile assumption about `resolve_uri`'s fallthrough; the `"://"` clause silently becomes dead/contradictory the day a real `ResolvedS3Url` variant is added.
- **The same blind spot lives in other callers** that trust `resolve_uri`'s `ResolvedLocalPath` to mean "local file" — e.g. the input normalizer and the image/document renderers (`load_binary_async(Path("s3://…"))`), and `_inputs_path_resolver.is_relative_local_path` (which would treat `s3://…` as a relative local path and prepend `base_dir`).

**Right-depth fix:** teach `resolve_uri` / `UriKind` to classify an unknown `<scheme>://` as a distinct non-local kind, and expose a single `is_local_uri(resolved) -> bool` predicate. Then the CSV hook and `_inputs_path_resolver` share one authoritative classifier (matching the project's "match/case over a typed enum, no string-sniffing" rule) and the `"://"` heuristic disappears. This is a `tools/uri` change with cross-caller impact → scope and test it on its own, not inside the CSV feature.

**Update (PR #955 review round 9):** the blind spot became a concrete bug — `_inputs_path_resolver.is_relative_local_path` was rewriting `s3://bucket/x.csv` into `<base_dir>/s3:/bucket/x.csv` on the CLI JSON-file path, defeating the CSV remote-url guard (codex/cubic). Fixed by adding the same `"://"`-in-resolved-path stopgap to `is_relative_local_path` (so scheme-bearing refs are left untouched and the remote guard fires). The `"://"` heuristic now lives in **two** callers (the CSV hook + `is_relative_local_path`); item A's typed `is_local_uri` predicate should replace both at once.

**Same root cause — local paths containing URL-reserved `?`/`#` (cubic, PR #955 round 1).** Suffix detection runs on `urlsplit(url).path` so a remote presigned `…csv?X-Amz-…` can't hide its suffix and slip past the local-only guard. The cost: a *local* file whose name literally contains `?` or `#` (POSIX-legal, Windows-illegal) has its suffix mis-stripped, so `data#1.csv` is not detected as tabular and falls through to record handling — a clear validation error, no data loss. The principled fix is the same `resolve_uri` scheme-classification above: resolve first, then take the suffix from the *resolved local path* (`?`/`#` are ordinary filename bytes there) for local refs and from `urlsplit` only for true URLs. Deferred with item A rather than bolted on as a second string heuristic. Niche (pathological local filename) and graceful, so not a v1 blocker.

### B. CSV detection + eager file I/O live in `StuffFactory`, the universal stuff constructor

A1 deliberately put the hook in `StuffFactory.make_stuff_from_stuff_content_or_data` (Case 2.5) so CSV input is reachable from the runner API and programmatic callers, not just the CLI. The consequence to weigh:

- `StuffFactory` is reached by **every** path that builds a stuff — CLI runs, runner-API input building, `WorkingMemory` re-hydration from a serialized payload, mock-input construction. All of them now perform eager local-disk I/O whenever a content dict carries a tabular-suffixed `url`.
- The CLI rewrites relative `url`s to absolute via `_inputs_path_resolver` **before** the factory sees them; non-CLI callers do **not**. A runner/programmatic caller passing `{"url": "data.csv"}` therefore opens a path resolved against the **process cwd**, and a re-hydrated `WorkingMemory` re-opens a path that may not exist on that host. (`test_eager_read_reflects_file_mutation` pins the disk-read-on-every-build behavior as intended.)

**Decision needed:** is eager file I/O at the factory altitude acceptable for all non-CLI callers, or should CSV reference resolution move up into a dedicated input-resolution layer (the design doc §2/§8 originally placed CSV parsing "in the input loader")? If the factory stays, document the relative-path-vs-cwd contract for non-CLI callers and decide whether re-hydration should re-read or carry the parsed list. (Note: Temporal is not shipped — don't over-weight the worker re-hydration angle, but the runner-API relative-path case is real today.)

## Deferred — documentation (fold into the Phase 5 docs page)

### C. `url`-field residual extends to multi-field records (A3/CT1) — RESOLVED (option b, PR #955 review round 1)

The documented A3/CT1 residual was "a single-record concept with a `url`-named field whose value ends `.csv` is read as a table". The hook originally keyed off `content.get("url")` **only**, so a content dict with *other* keys too — `{"label": "Home", "url": "report.csv"}` — was also hijacked into a table read, **silently dropping the sibling keys**.

**Fixed** by tightening detection to the single-key wrapper: `_try_make_csv_list_stuff` now returns `None` unless `set(content) == {"url"}`. A record with any sibling key stays an ordinary record (pinned by `test_record_with_csv_url_field_and_siblings_stays_record`). The residual is now strictly "a one-field `url` concept given `{"url": <tabular>}`", matching the documented limitation exactly. Codex + cubic both flagged the silent-drop; this removes it.

## Deferred — minor / cleanup (low priority, no decision needed)

- **Output-side error UX:** a non-flat / column-mismatched output raises `CsvFlatnessError`/`CsvColumnError` from `csv_from_list_content` **after** the pipeline succeeded; it surfaces via `execute_run`'s generic `except PipelexError` as "Failed to execute pipeline" rather than a tailored "Failed to --save-csv: …". Consider catching `CsvError` around the write block and re-emitting with the save-csv framing.
- **Suffix vocabulary drift:** `_TABULAR_SUFFIXES` (drives `is_tabular_path`) and `assert_supported_table_suffix`'s inline `.csv`/`.xlsx` literals are two independent authorities; express the latter in terms of the former before the `.xlsx`/`.tsv` codec ships.
- **Header-only CSV** yields an empty `ListContent` accepted by the hook, whereas the literal-empty-list path (Case 1.5) rejects empty lists — decide whether an empty CSV is a valid empty batch or should fail fast for parity.
- **Refined native concepts:** a concept that *refines* `Image`/`Document` has a non-native `concept_ref`, so `Concept.is_native_concept` is False and a `.csv`-suffixed `url` triggers the hook → `CsvFlatnessError` on the native content class. Niche; only matters if someone gives such a concept a `.csv` url.
- **Native-row list output:** `--save-csv` on a `Text[]` output writes a degenerate single-column `text` CSV instead of signalling the "flat structured list" contract. Acceptable or worth a clearer message — decide.
- **Small cleanups:** redundant `cast("dict[str, Any]", content)` in Case 2.5 and `cast("ListContent[StuffContent]", …)` in the save block; `get_optional_main_stuff()` vs the `pipe_output.optional_main_stuff` property (two spellings of one lookup); the two `if save_csv is not None:` blocks could be consolidated.
