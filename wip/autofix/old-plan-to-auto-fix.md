# Strategy: `pipelex fix` / `pipelex-agent fix` command

## Goal

A new standalone CLI command that auto-fixes deterministic issues in `.mthds` bundles, similar to `ruff check --fix`. Operates on bundle files only, accepts a list of paths.

Tier 1 only: all fixes are deterministic, no LLM involved, no iteration loop.

## CLI surface

### `pipelex-agent fix`

```
pipelex-agent fix my_method.mthds                                      # apply default fixes, show diff on stderr, write file
pipelex-agent fix my_method.mthds other.mthds                          # fix multiple bundles
pipelex-agent fix my_method.mthds --stdout                             # output fixed file to stdout (for agents)
pipelex-agent fix my_method.mthds --select strip-namespace,sync-controller-inputs
pipelex-agent fix my_method.mthds --ignore match-sequence-output
pipelex-agent fix my_method.mthds --prune                              # opt-in: also run prune-unreachable + prune-unused-concepts
```

### `pipelex fix`

```
pipelex fix my_method.mthds                                            # fix single bundle, show diff, write file
pipelex fix *.mthds                                                    # fix all bundles via shell glob
pipelex fix my_method.mthds --stdout                                   # fixed file to stdout
pipelex fix my_method.mthds --prune                                    # opt-in pruning
```

### Rule categories

Rules are split into two groups with different defaults:

| Group | Rules | Default |
|-------|-------|---------|
| **Correction rules** | `strip-namespace`, `strip-native-concept-redecl`, `sync-controller-inputs`, `match-sequence-output`, `fix-list-notation` | ON — always applied unless `--ignore`'d |
| **Pruning rules** | `prune-unreachable`, `prune-unused-concepts` | OFF — require `--prune` or explicit `--select` |

`--prune` is a shorthand for `--select prune-unreachable,prune-unused-concepts` on top of the default correction rules. It can combine with `--ignore` to still exclude specific correction rules.

`--select` and `--ignore` are mutually exclusive.

### Output behavior

| Mode | stdout | stderr | File |
|------|--------|--------|------|
| Default | JSON result with `fixes_applied` array | unified diff of changes | written in-place |
| `--stdout` | fixed `.mthds` content | unified diff + JSON diagnostics | untouched |

When multiple bundles are passed, `--stdout` is an error (ambiguous output). Each bundle is fixed independently; the JSON result contains a per-bundle summary.

The diff is always shown on stderr when fixes are applied. Suppress with `--quiet`.

### JSON output (agent CLI)

Single bundle:

```json
{
  "success": true,
  "bundle_path": "/path/to/bundle.mthds",
  "fixed": true,
  "fixes_applied": [
    {
      "fix_code": "strip-namespace",
      "pipe_code": "my_domain.generate_report",
      "message": "Stripped same-domain prefix 'my_domain.' from pipe code",
      "line": 12
    },
    {
      "fix_code": "sync-controller-inputs",
      "pipe_code": "run_pipeline",
      "message": "Synced inputs with needed_inputs(): added 'topic', removed 'unused_var'"
    }
  ],
  "remaining_errors": [...],
  "validated_pipes": [...]
}
```

Multiple bundles:

```json
{
  "success": true,
  "bundles": [
    {
      "bundle_path": "/path/to/a.mthds",
      "fixed": true,
      "fixes_applied": [...],
      "remaining_errors": []
    },
    {
      "bundle_path": "/path/to/b.mthds",
      "fixed": false,
      "fixes_applied": [],
      "remaining_errors": [...]
    }
  ]
}
```

When no fixes are needed and validation passes, `fixed: false` with empty arrays.

### Fixability annotations on `validate` errors

Independently of the `fix` command, the existing `pipelex-agent validate` output gains `fixable`/`fix_code` annotations per validation error, so agents know which errors are auto-fixable:

```json
{
  "validation_errors": [
    {
      "category": "pipe_validation",
      "error_type": "MISSING_INPUT_VARIABLE",
      "pipe_code": "my_pipe",
      "fixable": true,
      "fix_code": "sync-controller-inputs"
    }
  ]
}
```

## Fix rules (Tier 1)

### Correction rules (default ON)

#### `strip-namespace` — Remove same-domain pipe code prefixes

**Triggers on:** Pipe codes containing `.` where the prefix matches the bundle's own domain.

**What it does:** `my_domain.generate_report` -> `generate_report` when the bundle's `domain = "my_domain"`. Applies to:
- Pipe definition keys (`[pipe.my_domain.foo]` -> `[pipe.foo]`)
- `main_pipe` value
- Internal references: `steps`, `branches`, `branch_pipe_code`, `outcomes` values, `default_outcome`

Does NOT strip cross-domain references (different domain prefix) — those are legitimate qualified refs.

**Error types that trigger it:** `INVALID_PIPE_CODE_SYNTAX` (when caused by dotted codes)

**Legacy reference:** `builder_loop.py:590-701` (`_strip_namespace_from_pipe_codes`), specifically the `_should_strip_ref()` helper at lines 648-657 which checks whether the bare code exists in the bundle or the dotted prefix matches the bundle's domain.

#### `strip-native-concept-redecl` — Remove redeclared native concepts

**Triggers on:** Concept definitions whose key matches a built-in native concept (Text, Image, Document, etc.).

**What it does:** Removes the entire `[concept.Text]` section (or inline `concept.Text = "..."`) since native concepts must not be redeclared.

**Error types that trigger it:** Concept factory errors when a declared concept shadows a native one.

**Legacy reference:** `builder_loop.py:556-570` (`_strip_native_concept_declarations`). Uses `NativeConceptCode.values_list()` to identify builtins.

**Current codebase reference:** `pipelex/core/concepts/native/concept_native.py` for `NativeConceptCode`.

#### `sync-controller-inputs` — Align controller pipe inputs with their requirements

**Triggers on:** `MISSING_INPUT_VARIABLE` or `EXTRANEOUS_INPUT_VARIABLE` errors on controller pipes (PipeSequence, PipeParallel, PipeBatch, PipeCondition).

**What it does:** Replaces the `inputs` table of the controller pipe with the exact set from its `needed_inputs()`. This works because controller inputs are fully derivable from the child pipes they orchestrate.

**Legacy reference:** `builder_loop.py:784-811` (`_fix_bundle_validation_error`, MISSING/EXTRANEOUS handler). Calls `pipe.needed_inputs()` and rebuilds the input dict.

**Current codebase reference:**
- `pipelex/core/pipes/exceptions.py:103-104` for `PipeValidationErrorType.MISSING_INPUT_VARIABLE` / `EXTRANEOUS_INPUT_VARIABLE`
- Each controller pipe class exposes `needed_inputs()` which returns the correct input set

#### `match-sequence-output` — Fix sequence output to match last step

**Triggers on:** `INADEQUATE_OUTPUT_CONCEPT` or `INADEQUATE_OUTPUT_MULTIPLICITY` errors on PipeSequence pipes.

**What it does:** Sets the sequence's `output` to the output concept (with multiplicity) of its last step. A sequence's output is always its last step's output — this is a structural invariant.

**Legacy reference:** `builder_loop.py:813-835`. Gets the last step's pipe, reads its output concept and multiplicity, updates the sequence's output.

#### `fix-list-notation` — Add `[]` for multiplicity mismatches

**Triggers on:** Dry-run errors where a PipeCompose field receives `ListContent` but expects a scalar type.

**What it does:** Adds `[]` to the input concept reference. E.g., `inputs = { items = "MyItem" }` -> `inputs = { items = "MyItem[]" }`.

**Legacy reference:** `builder_loop.py:909-966` (`_fix_dry_run_compose_multiplicity_mismatch`) and `builder_loop.py:968-1027` (`_fix_single_multiplicity_mismatch`). Parses the dry-run error message regex to identify the pipe, field, and expected type.

### Pruning rules (default OFF, opt-in via `--prune`)

#### `prune-unreachable` — Remove pipes not reachable from main_pipe

**Triggers on:** Bundle contains pipe definitions that are never referenced from `main_pipe` (directly or transitively).

**What it does:** Walks the call graph starting from `main_pipe`, collecting all reachable pipe codes via:
- PipeSequence -> `steps[*].pipe_code`
- PipeParallel -> `branches[*].pipe_code`
- PipeBatch -> `branch_pipe_code`
- PipeCondition -> `outcomes` values + `default_outcome` (excluding special outcomes)

Removes all pipe definitions not in the reachable set.

**Legacy reference:** `builder_loop.py:340-394` (steps A-B of `_prune_unreachable_specs`). The graph walk is at lines 358-388.

#### `prune-unused-concepts` — Remove concepts not referenced by any pipe

**Triggers on:** Bundle contains concept definitions not referenced by any reachable pipe or by any other used concept (transitively).

**What it does:**
1. Collect concept refs from all reachable pipes (output, inputs, combined_output)
2. Transitively walk concept definitions: if concept A refines concept B or has a structure field referencing concept C, then B and C are also used
3. Remove concept definitions not in the transitive closure

**Legacy reference:** `builder_loop.py:396-424` (steps C-E of `_prune_unreachable_specs`). Helper methods: `_collect_concept_refs_from_pipe_spec` (lines 452-488), `_collect_concept_refs_from_concept_spec` (lines 491-523), `_extract_local_bare_code` (lines 428-450).

## Architecture

### Processing pipeline

```
read .mthds file (raw text)
    |
    v
parse to PipelexBundleBlueprint (existing interpreter)
    |
    v
run validation (existing validate_bundle), catch errors
    |
    v
match errors to fix rules
    |
    v
apply fixes to TOML document (tomlkit, preserves formatting)
    |
    v
re-validate to confirm fixes worked
    |
    v
output: diff + fixed content + JSON report
```

### TOML-level rewriting

The key challenge: fixes must operate on the TOML source (to preserve comments, ordering, formatting) rather than on Python objects.

We use **tomlkit** (already a dependency, used throughout the codebase) which provides a DOM-like TOML representation that preserves comments, whitespace, and inline table style.

### Code layout

```
pipelex/pipeline/
    validate_bundle.py              # existing validation logic (unchanged)
    fix_bundle.py                   # NEW: orchestrator (fix_bundle, fix_bundles)
    fix_rules/                      # NEW: one module per fix rule
        __init__.py                 # registry: ALL_RULES, DEFAULT_RULES, PRUNING_RULES
        base.py                     # FixRule ABC, FixResult model, FixRuleCategory enum
        strip_namespace.py
        strip_native_concept_redecl.py
        sync_controller_inputs.py
        match_sequence_output.py
        fix_list_notation.py
        prune_unreachable.py
        prune_unused_concepts.py

pipelex/cli/
    agent_cli/commands/
        fix_cmd.py                  # NEW: pipelex-agent fix
    commands/
        fix_cmd.py                  # NEW: pipelex fix
```

### Fix rule interface

```python
class FixRuleCategory(StrEnum):
    CORRECTION = "correction"   # default ON
    PRUNING = "pruning"         # default OFF, opt-in via --prune


class FixResult(BaseModel):
    fix_code: str
    pipe_code: str | None = None
    concept_code: str | None = None
    message: str
    line: int | None = None


class FixRule(ABC):
    code: str                       # e.g. "strip-namespace"
    category: FixRuleCategory
    description: str

    @abstractmethod
    def apply(
        self,
        toml_doc: TOMLDocument,
        blueprint: PipelexBundleBlueprint,
        validation_error: ValidateBundleError | None,
    ) -> list[FixResult]:
        """Mutate toml_doc in place. Return list of fixes applied."""
```

Each rule receives:
- The **tomlkit document** (mutable, preserves formatting) for making changes
- The **parsed blueprint** (read-only) for understanding the bundle structure
- The **validation error** (if any) for matching specific error types

### Execution order

Rules execute in a defined order (not arbitrary) because some fixes enable others:

1. `strip-namespace` — must run first, unlocks correct pipe code resolution for all subsequent rules
2. `strip-native-concept-redecl` — removes invalid concepts before input/output analysis
3. `sync-controller-inputs` — needs correct pipe codes and concepts
4. `match-sequence-output` — needs correct pipe codes
5. `fix-list-notation` — needs dry-run results, runs after structural fixes
6. `prune-unreachable` — cleanup pass, runs after all pipe fixes (opt-in)
7. `prune-unused-concepts` — cleanup pass, runs last, depends on prune-unreachable (opt-in)

### Orchestrator

```python
# In fix_bundle.py
async def fix_bundle(
    mthds_file_path: Path,
    selected_rules: list[str] | None = None,
    ignored_rules: list[str] | None = None,
    prune: bool = False,
    library_dirs: Sequence[Path] | None = None,
) -> FixBundleResult:
    raw_text = mthds_file_path.read_text()
    toml_doc = tomlkit.parse(raw_text)

    # Phase 1: validate to get errors
    blueprint, validation_error = _validate_and_catch(mthds_file_path, library_dirs)

    # Phase 2: resolve which rules to run
    rules = _resolve_rules(selected_rules, ignored_rules, prune)

    # Phase 3: apply fix rules in order
    all_fixes: list[FixResult] = []
    for rule in rules:
        fixes = rule.apply(toml_doc, blueprint, validation_error)
        all_fixes.extend(fixes)

    if not all_fixes:
        return FixBundleResult(fixed=False, fixes=[], original=raw_text, result=raw_text)

    fixed_text = tomlkit.dumps(toml_doc)

    # Phase 4: re-validate to confirm
    remaining_error = _validate_text_and_catch(fixed_text, library_dirs)

    return FixBundleResult(
        fixed=True,
        fixes=all_fixes,
        original=raw_text,
        result=fixed_text,
        remaining_errors=remaining_error,
    )


def _resolve_rules(
    selected: list[str] | None,
    ignored: list[str] | None,
    prune: bool,
) -> list[FixRule]:
    if selected and ignored:
        msg = "--select and --ignore are mutually exclusive"
        raise ValueError(msg)
    if selected:
        return [rule for rule in ALL_RULES if rule.code in selected]
    active = list(DEFAULT_RULES)
    if prune:
        active.extend(PRUNING_RULES)
    if ignored:
        active = [rule for rule in active if rule.code not in ignored]
    return active
```

## What is NOT in scope (Tier 1)

- No LLM-based fixes (generating missing concepts, inferring outputs for conditions)
- No `fix-input-stuff-mismatch` (requires understanding concept compatibility — judgment call)
- No `fix-compose-structure` (updating concept structure fields for list types — too close to authoring)
- No `fix-condition-output` (choosing output for PipeCondition with mixed branch outputs — ambiguous)
- No iteration loop (fixes are convergent in a single pass)
- No `plxt fmt` integration (can be run separately by the caller)

These are candidates for a future Tier 2 (`--fix --unsafe`).
