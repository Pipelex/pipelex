# Line endings: the writer-by-writer half

Surfaced by the U4 fix on `feature/Codegen-followups` (PR #1127), during the `/review` pass on 2026-08-19. **Not a codegen item** — U4 is closed and every codegen write path is covered. This is the pre-existing repo-wide residue that U4 made visible, and it is deliberately not part of that PR.

## What is already done

`.gitattributes` now carries `* text=auto eol=lf`, so every **tracked** file is normalised to LF in the index and on checkout whatever the platform. That closes the user-visible half of the problem — no churning diffs, no CRLF landing in a commit — and it cost one line. No tracked file contained CRLF when it landed, so it introduced no renormalisation diff.

## What is left, and why it still matters

`.gitattributes` fixes the files git owns. It does not fix the writers, and two things still follow from that:

- A file written **outside** a git checkout (a consumer's output directory, a temp tree, a container) still lands with the host's line endings.
- A content hash taken over an in-memory LF string still stops describing the bytes on disk, which is the property `save_text_to_path` was fixed to restore.

Each site below writes a **tracked** artifact today and passes no `newline` argument, so Python translates every `\n` to `os.linesep`. The fix in each case is the same one U4 applied: route the write through `pipelex.tools.misc.file_utils.save_text_to_path`, which passes `newline="\n"`.

| Site | Writes | Gated by |
|---|---|---|
| `pipelex/kit/single_file_agent_rules.py:139` | repo-root `CLAUDE.md`, `AGENTS.md` | `make check-rules` |
| `pipelex/tools/misc/toml_utils.py:75` (`save_toml_to_path`) | `subject_grants.toml`, `.drift/acks/*.toml` | `make check-keyword-only`, `make drift-check` |
| `pipelex/migration/goldens.py:105,112` | `pipelex/migration/goldens/**` | `make check-migration-schemas`, `make check-ledger` |
| `pipelex/errors/error_pages_generator.py:367` | `docs/errors/*.md` | `make docs-check` |
| `pipelex/cli/dev_cli/commands/generate_error_identity_cmd.py:44` | `tests/data/errors/error_identity.txt` | `test_error_identity_snapshot.py` |
| `pipelex/cli/dev_cli/commands/duration_map.py:66` | `.test_durations` | `test_test_durations_paths.py` |
| `pipelex/cli/dev_cli/commands/update_gateway_models_cmd.py:142-143` | the gateway model reference pairs | `make check-gateway-models` |
| `pipelex/cli/dev_cli/commands/keyword_only_guard.py:923` | any `pipelex/**/*.py` the fixer rewrites | `make check-keyword-only` |
| `pipelex/cli/dev_cli/commands/refresh_graph_ui_sri_cmd.py:198` | `pipelex/graph/reactflow/standalone_assets.py` | manual |
| `pipelex/graph/graph_factory.py:159-177` | graphspec JSON, Mermaid, ReactFlow HTML | not tracked; user output |
| `pipelex/cogt/models/deck_manifest.py:160` | `.pipelex/inference/deck/.kit_manifest.json` | not diff-gated |

`save_toml_to_path` is the one that is not a one-liner: it hands an open file to `tomlkit.dump` rather than writing a string, so it needs `open(path, "w", encoding="utf-8", newline="\n")` instead of a call swap.

## The trap that hid this

The sweep behind U4 grepped for `os.linesep` and found nothing, which read as a clean bill. That is the wrong probe: the bug is the **absence** of an explicit `newline="\n"`, never the presence of `os.linesep`. Grep for `write_text(` and `open(..., "w")` instead.

The second trap is why none of the gates above would have caught it. Every one of them compares a freshly rendered string against `path.read_text(...)`, and that read uses universal newlines — so it folds CRLF back to LF *before* the comparison. A CRLF-corrupted committed file passes its own freshness check while being byte-different from what the tool writes. The check is blind to exactly the corruption it looks like it would catch.

## Known, and deliberately left alone

- **`keyword_only_guard.py` reads with translation too**, so its CRLF-preservation branch in `fix_source` — the one `test_crlf_line_endings_preserved_and_fixed` pins byte-for-byte — is unreachable through the only caller that touches the filesystem. Fixing the write without deciding the read leaves it half-done. The open question is whether the fixer should genuinely preserve CRLF (read and write with `newline=""`) or declare itself LF-only and delete the branch. Decide that on its own terms.
- **`load_text_from_path` still reads with universal newlines** while `save_text_to_path` now writes verbatim. One consequence is worth knowing rather than fixing: a generated file already on disk as CRLF reads back as LF, compares equal to the canonical content, and is therefore never rewritten by `_write_if_changed` — so the LF fix does not heal a tree that was already corrupted, it only stops new corruption. The tree is stable either way (nothing rewrites it, so nothing churns), which is why this is a note and not a bug.
