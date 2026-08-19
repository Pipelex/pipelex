# PR #1128 — deferred review finding

Surfaced while triaging the review-agent comments on PR #1128 (`feature/Line-endings-sweep`) on 2026-08-19. Everything else the bots raised was either fixed on the branch or resolved as a false positive; this is the one item deliberately left for later, because it is well outside the PR and wants its own test pass.

## `is_snake_case` accepts a trailing newline

`pipelex/tools/misc/string_utils.py:282` anchors its pattern with `$`:

```python
def is_snake_case(word: str) -> bool:
    return re.match(r"^[a-z][a-z0-9_]*$", word) is not None
```

In Python `$` matches at the end of the string **or immediately before a trailing newline**, so `is_snake_case("abc\n")` returns `True` while `is_snake_case("abc\ndef")` correctly returns `False`. Verified by execution.

That admits a pipe code or domain code ending in a newline through the two validators built on it: `pipelex/pipe_machinery/validation.py:126` (`is_pipe_code_valid`) and `pipelex/core/domains/validation.py:26`, both wired into the bundle parser at `pipelex/mthds_parsing/pipelex_bundle_blueprint.py:113-121` and `:149,181`.

**Why it was not fixed here.** It reached this review only as a side question — whether a `pipe_ref` could carry a line terminator into a codegen stamp header. Through the stamp it cannot do harm either way: a raw `\n` breaks the header line under any split rule, so the stamp gate rejects it, and no codegen caller populates `pipe_ref` in the first place. The gap is real but it belongs to identifier validation generally, not to codegen.

**The fix and what it costs.** Swap `$` for `\Z`, which matches only at the true end of the string. The change is one character, but it tightens every code that flows through those two validators, so it wants a deliberate pass: a test for the trailing-newline case on both validators, and a check that no fixture or example bundle in the tree currently relies on the loose behaviour.
