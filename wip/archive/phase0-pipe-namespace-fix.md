# Pipe Namespace Fix: Domain-Qualified `pipe_ref`

> **Status**: Technical spec — Phase 0 of the master plan
> **Date**: 2026-03-23
> **Related**: [00-master-plan.md](00-master-plan.md), [archive/early-library-as-execution-context.md](archive/early-library-as-execution-context.md)

---

## 1. Problem

Pipes and concepts have asymmetric namespace behavior in the library.

**Concepts** are indexed by `concept_ref` = `domain.ConceptCode` (e.g., `scoring.WeightedScore`). Two concepts with the same code in different domains coexist without conflict. This is correct.

**Pipes** are indexed by bare `code` (e.g., `compute_score`, not `scoring.compute_score`). If two domains define a pipe with the same code, the second collides with the first.

### Where the asymmetry lives

| Component | Concept key | Pipe key |
|-----------|-------------|----------|
| `ConceptLibrary.root` | `concept_ref` = `domain.Code` | — |
| `PipeLibrary.root` | — | bare `code` |
| `add_new_concept()` | checks `concept.concept_ref` | — |
| `add_new_pipe()` | — | checks `pipe.code` |
| `get_optional_concept()` | looks up by `concept_ref` | — |
| `get_optional_pipe()` | looks up by bare `code`, domain validation is a fallback | — |

### Code references

- `PipeLibrary.add_new_pipe()` at `pipe_library.py:39-48`: keys by `pipe.code`
- `PipeLibrary.get_optional_pipe()` at `pipe_library.py:56-82`: primary lookup by bare code, domain-qualified lookup is a fallback that still resolves to bare code internally
- `ConceptLibrary.add_new_concept()` at `concept_library.py:81-85`: keys by `concept.concept_ref`
- `library_manager.py:378`: `pipe_source_in_this_load` tracks by bare `pipe_code`
- `library_manager.py:402`: `_pipe_source_map` tracks by bare `pipe_code`

### Additional issue: Domain merging

`DomainLibrary.add_domain()` at `domain_library.py:32-37` raises if the domain already exists. This prevents multiple bundles from contributing to the same domain — a legitimate use case (e.g., `scoring_core.mthds` and `scoring_advanced.mthds` both declaring `domain: scoring`).

---

## 2. The Fix

### 2.1 Add `pipe_ref` to `PipeAbstract`

```python
# pipelex/core/pipes/pipe_abstract.py
class PipeAbstract(ABC, BaseModel):
    code: str
    domain_code: str
    # ...

    @property
    def pipe_ref(self) -> str:
        """Domain-qualified pipe reference, e.g. 'scoring.compute_score'."""
        return f"{self.domain_code}.{self.code}"
```

This mirrors `concept_ref` on `Concept` (which is `domain.ConceptCode`).

### 2.2 Rekey `PipeLibrary`

```python
# pipelex/libraries/pipe/pipe_library.py
PipeLibraryRoot = dict[str, PipeAbstract]  # key changes from code to pipe_ref

def add_new_pipe(self, pipe: PipeAbstract):
    if pipe.pipe_ref in self.root:
        msg = f"Pipe '{pipe.pipe_ref}' already exists in the library. ..."
        raise PipeLibraryError(msg)
    self.root[pipe.pipe_ref] = pipe
```

### 2.3 Update lookup methods

`get_optional_pipe()` needs to handle three lookup forms:

1. **Domain-qualified** (`scoring.compute_score`): Direct lookup by `pipe_ref` — this becomes the primary path
2. **Bare code** (`compute_score`): Search across all domains. If exactly one match, return it. If multiple matches (same code in different domains), raise ambiguity error. If zero matches, return None.
3. **Cross-package** (`alias->scoring.compute_score` or `alias->compute_score`): Existing aliased lookup, adjusted for `pipe_ref` keying

```python
def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
    # 1. Direct lookup (works for pipe_ref and cross-package keys)
    pipe = self.root.get(pipe_code)
    if pipe is not None:
        return pipe

    # 2. Cross-package refs
    if QualifiedRef.has_cross_package_prefix(pipe_code):
        alias, remainder = QualifiedRef.split_cross_package_ref(pipe_code)
        # Try domain-qualified remainder
        pipe = self.root.get(f"{alias}->{remainder}")
        if pipe is not None:
            return pipe
        # Try bare code remainder — search aliased entries
        if "." not in remainder:
            # ... search alias->domain.code entries
            pass
        return None

    # 3. Bare code — search across domains
    if "." not in pipe_code:
        matches = [p for p in self.root.values() if p.code == pipe_code]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            domains = [p.domain_code for p in matches]
            msg = f"Ambiguous pipe code '{pipe_code}' found in domains: {domains}. Use domain-qualified ref."
            raise PipeLibraryError(msg)
        return None

    return None
```

### 2.4 Update `library_manager.py`

In `load_from_blueprints()`:
- `pipe_source_in_this_load` should key by `pipe_ref` (= `f"{blueprint.domain}.{pipe_code}"`)
- `_pipe_source_map` should key by `pipe_ref`

### 2.5 Fix domain merging

Domains are namespace metadata — they carry `code`, `description`, and `system_prompt`. Since the LibraryCrate is flat (no domain-level grouping), domains exist only in the live `Library` as lightweight metadata objects extracted from the refs.

`DomainLibrary.add_domain()` should be idempotent for re-adds of the same domain:

```python
def add_domain(self, domain: Domain):
    domain_code = domain.code
    if domain_code in self.root:
        # Same domain from another bundle — idempotent (Domain is just namespace metadata)
        return
    self.root[domain_code] = domain
```

Since domains carry no meaningful runtime state beyond the namespace itself, simple idempotency is sufficient. The `system_prompt` field on Domain is a legacy convenience (PipeLLM fallback) that should be inlined at pipe factory time before crate construction.

---

## 3. Migration: Call Sites to Update

Every place that passes a bare pipe code as a lookup key needs to be audited. Most will continue to work because the bare-code fallback handles unambiguous lookups. But some sites may need to pass domain-qualified refs.

### Direct `get_required_pipe()` / `get_optional_pipe()` callers

These are the 41 files identified in the investigation. Key categories:

- **Pipe controllers** (`sub_pipe.py`, `pipe_sequence.py`, `pipe_batch.py`, `pipe_parallel.py`, `pipe_condition.py`): These call `get_required_pipe()` with the sub-pipe code from the blueprint. Currently bare codes. If the pipe is in the same domain, the bare code lookup will find it (unambiguous). If cross-domain, the blueprint already uses domain-qualified or cross-package refs.

- **Pipeline setup** (`pipeline_run_setup.py`, `pipeline_manager.py`): Calls `get_required_pipe(pipe_code=pipe_code)` where `pipe_code` comes from user input or `main_pipe`. User input may be bare or qualified — the fallback handles both.

- **Hub helpers** (`hub.py`): Thin wrappers, no change needed beyond forwarding.

- **Temporal routers** (`pipe_router_top.py`, `pipe_router_child.py`): Same pattern as pipeline setup.

- **CLI commands**: Various show/validate/run commands that resolve pipes by code. Should work via fallback.

### `_pipe_source_map` consumers

`library_manager.py` uses `_pipe_source_map` to track which file a pipe came from. Must rekey by `pipe_ref`. Check `get_pipe_source()` method.

### Tests

Existing test helpers that create pipes and add them to libraries will need to provide `domain_code` for proper `pipe_ref` generation. Check all test fixtures and factories.

---

## 4. Test Plan

### Unit tests for `PipeLibrary`

1. **Multi-domain coexistence**: Create two pipes with same code (`compute_score`) in different domains (`scoring`, `analytics`). Add both to same `PipeLibrary`. Both exist and are retrievable by `pipe_ref`.

2. **Domain-qualified lookup**: Look up `scoring.compute_score` → returns scoring domain's pipe. Look up `analytics.compute_score` → returns analytics domain's pipe.

3. **Bare-code unambiguous**: When only one pipe with code `compute_score` exists, bare lookup `compute_score` returns it.

4. **Bare-code ambiguous**: When two domains both have `compute_score`, bare lookup `compute_score` raises `PipeLibraryError` with helpful message listing the domains.

5. **Cross-package refs still work**: `alias->scoring.compute_score` lookup works with `pipe_ref`-keyed entries.

### Unit tests for `DomainLibrary`

6. **Domain idempotency**: Add domain `scoring` twice → no error, domain exists once.

### Integration tests

7. **Load multi-bundle same domain**: Create two `.mthds` files both declaring `domain: scoring` with different pipes. Load both. All pipes accessible. Domain exists once.

8. **Full pipeline through multi-domain library**: A PipeSequence referencing pipes from multiple domains runs correctly.

### Regression

9. **All existing tests pass**: `make agent-test` green.
