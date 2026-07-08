# Deferred: the duplicated `"://"` scheme stopgap (make `resolve_uri` classify unknown schemes)

**Status:** deferred design tradeoff — **no live bug**, fully tested. Surfaced by the PR #1032 cubic-dev-ai review ([thread](https://github.com/Pipelex/pipelex/pull/1032) on `stuff_factory.py`). The acknowledgment already lived in a code comment; this note promotes it so the follow-up isn't lost.

## What the reviewer flagged (verified — the duplication is real)

`resolve_uri` (`pipelex/tools/uri/uri_resolver.py`) only recognizes `data:` / `pipelex-storage://` / `file://` / `http(s)://`; **everything else falls into `ResolvedLocalPath`**. So an unrecognized scheme like `s3://bucket/x.csv` or `gs://bucket/x.csv` arrives as a `ResolvedLocalPath` whose `.path` still contains `"://"`. Two independent sites bolt on the same `"://"` check to compensate — treat such a value as *not* a genuine local path:

- `uri_resolver.py` → `is_relative_local_path()`: `if "://" in resolved.path: return False` — so a scheme-like value is never rewritten as relative (it would otherwise be mangled into `<base_dir>/s3:/bucket/x`). Shared by the shaper's file/CSV arms (via `resolve_local_path_reference`) and the CLI url-key walk (`_inputs_path_resolver`).
- `stuff_factory.py` → `try_make_csv_list_content()`: `if not isinstance(resolved, ResolvedLocalPath) or "://" in resolved.path:` — the CSV local-only guard, raising a redacted `CsvError` for a remote/scheme url. Shared by the bottom-up factory (Case 2.5 envelope) and the top-down `InputShaper._try_shape_csv`.

The existing code already names this a stopgap (`uri_resolver.py`, in `is_relative_local_path`'s body): *"Mirrors the same `"://"` stopgap in the CSV input hook; both go away once `resolve_uri` classifies schemes (tools/uri follow-up)."*

## Why this is deferred, not fixed now

- **No live bug.** All sites behave identically today; `s3://` / `gs://` are correctly left-untouched / rejected, with coverage at `tests/unit/pipelex/core/memory/input_shaper/test_file_paths.py` (remote/scheme params), `tests/unit/pipelex/cli/test_inputs_path_resolver.py` (`S3_URL`, `GS_URL`), and `tests/integration/pipelex/csv/test_csv_input_detection.py`.
- **The reviewer's "top-down vs bottom-up CSV flows drift apart" framing is imprecise.** Both CSV flows converge on the *same* line in `try_make_csv_list_content`, so CSV scheme-rejection is not duplicated between them. The real duplication is the CSV guard vs. the relative-path resolver — two sites, not two CSV flows.
- **The proper fix broadens the URI-classification contract** — out of this PR's scope (it's Smart Inputs D3/D11, not a URI-tools refactor). Per the project's "defer design tradeoffs, don't reflexively apply" convention, it waits for a deliberate `tools/uri` pass.
- The drift risk is modest-but-real: if someone tightened one site (e.g. switched to `urlsplit().scheme`) without the other, they'd diverge — but the tests above guard against silent divergence.

## The fix (when `tools/uri` is next touched)

- **Proper (root cause):** make `resolve_uri` classify unknown schemes — add a `ResolvedUnknownScheme` / `UriKind` variant in `pipelex/tools/uri/resolved_uri.py` and update every exhaustive `match ResolvedUri` (`extract_filename_from_uri`, `describe_uri`, `make_base64_url_from_any_uri`). Then both `"://"` band-aids delete: `is_relative_local_path` and the CSV guard branch on the typed variant instead.
- **Partial (if a smaller step is wanted first):** extract `path_has_unrecognized_scheme(path) -> bool` in `tools/uri` and call it from both sites — consolidates the two checks into one place but keeps the heuristic.

Prefer the proper fix; the partial one only removes the duplication, not the stopgap.
