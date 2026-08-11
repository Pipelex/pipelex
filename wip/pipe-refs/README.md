# Bare references resolve across domains; the standard says they must not

**Status (2026-08-11).** Decided: tighten the runtime to the standard, implemented via build-time qualification of in-body references. The design and phased plan are in [build-time-qualification.md](build-time-qualification.md); §7 below was its starting sketch and is superseded by that document. The evidence in §1–§6 remains the record of why.

**What this is.** A decision brief for the divergence recorded in [`../parity/bare-pipe-ref-spec-divergence.md`](../parity/bare-pipe-ref-spec-divergence.md), which closed with *"the direction of the fix is genuinely open"* and deferred it. This directory re-opens it with measurements instead of priors, and adds two things that note does not contain: the rule turns out to be **load-bearing for `[exports]`**, and the same divergence is **still live for concepts**, one file over from the pipes that were fixed.

**Everything below is reproducible from this checkout.** Two probe scripts and a demo generator live in [`probes/`](probes/); every number and every quoted error in this document was produced by them against this tree. Nothing here is inferred from reading code alone.

**What is being asked of the reader.** Confirm or refute the claims in §1–§5 (each names the file, the line, and the command), then plan the change sketched in §7. Do not treat §7 as settled — it is a proposal, and §8 lists what would have to be true for it to be right.

---

## 1. The rule

The normative text is in the sibling `mthds/` repo (the open standard, published to mthds.ai), not here, so a fresh clone cannot resolve the path. From `mthds/docs/spec/namespace-resolution.md`:

> ## Resolution Order for Bare Pipe References
>
> 1. **Current bundle** — check pipes declared in the same `.mthds` file.
> 2. **Same domain, other bundles** — if the bundle is part of a package, check pipes in other bundles that declare the same domain.
> 3. **Error** — if not found, the reference is invalid.
>
> Bare pipe references do NOT fall through to other domains or other packages.

The same page states the identical rule for concepts (§ *Resolution Order for Bare Concept References*, with natives taking priority at step 1).

Two other sections of that same page **depend** on this rule. They are quoted in §3, because they are the part of the argument the deferred note does not have.

## 2. What this repository does today

> **HISTORICAL as of the pipe-side fix.** The table below records the state that motivated this work, and it is kept as written rather than rewritten — the argument only makes sense against the disagreement it describes. What changed: the pipe readers now qualify a bare in-body ref to its **owner domain** and the live `PipeLibrary` lookup no longer searches across domains, so the two pipe rows agree with each other *and* with the standard. Bare codes a human types at an entry point keep working through a separate, explicitly-named affordance (`get_optional_entry_pipe`), which searches crate-wide and refuses ambiguity. **The concept rows are still accurate** — the concept-side work is not done. Re-measured outcomes are in §3.

Four readers of one authored fact. They do not agree, and only one of them agrees with the standard.

| Reader | Where | Bare ref behaviour |
| --- | --- | --- |
| `PipeLibrary.get_optional_pipe` | `pipelex/libraries/pipe/pipe_library.py` (step 3, since deleted) | Searches **every** domain (`# 3. Bare code fallback — search across domains`); one match wins, several raise `PipeLibraryError` |
| `_qualify_pipe_ref` | then `crate_normalization.py`, now `crate_qualification.py` | Same crate-wide search, **deliberately** mirrored onto the normalizer so the two readers agree (PR #1085) |
| `_qualify_concept_ref` | then `crate_normalization.py`, now `crate_qualification.py` | Qualifies as `<owner domain>.<Code>`, no search — **this one matches the standard** |
| `ConceptLibrary.get_required_concept_from_concept_ref_or_code` | `pipelex/libraries/concept/concept_library.py` | With `search_domain_codes=None`, walks every concept in the library and raises on a collision — the same shape as the pipe fallback |

So: **pipes** agree with each other and disagree with the standard. **Concepts** disagree with each other — the normalizer complies, the live library does not. The pipe fix chose which reader to move; it moved the normalizer *away* from the standard, and it did not touch concepts.

Note also where normalization runs: `normalize_crate` is called from `pipelex/pipeline/resolve_bundle.py:86`, `pipelex/cli/commands/crate_loading.py:43` and `pipelex/cli/commands/build/runner/_runner_core.py:107` — the `resolve` / `codegen` / `build` paths. The ordinary library load that backs `pipelex run` does **not** normalize, so the live `PipeLibrary` really does see bare in-body refs at run time. Any plan that hopes to fix this purely in the normalizer has to deal with that first.

## 3. The rule is a visibility boundary, not a lookup convenience

This is the argument that changes the question, and it is checkable in one run.

The standard exempts bare references from the export check **because** they cannot leave their domain (`mthds/docs/spec/namespace-resolution.md` § *Visibility Rules (Intra-Package)*):

> - **Cross-domain references** (within the same package) — the target pipe MUST be exported. […]
> - **Bare references** — always allowed at the visibility level (they resolve within the same domain).

The visibility checker implements the exemption literally. `mthds/package/visibility.py:82-84` (the installed `mthds` package, reached from `pipelex/libraries/visibility_utils.py:53`, called at `pipelex/libraries/library_manager.py:847`):

```python
# Bare ref -> always allowed (no domain check)
if not pipe_ref.is_qualified:
    return True
```

Combine that with a resolver that *does* let bare refs leave their domain and you get an **export bypass**: the reference form that skips the check is the one that reaches the other domain. Measured, on this tree:

```sh
DEMOS=$(./wip/pipe-refs/probes/make-demos.sh | tail -1)
( cd "$DEMOS/export-bypass"          && pipelex resolve . )   # bare `helper`
( cd "$DEMOS/export-bypass-control"  && pipelex resolve . )   # qualified `beta.helper`
```

One package, one manifest, `beta.helper` deliberately absent from `[exports]`. The two runs differ only in how `alpha.run_flow` spells its step:

| Step written as | Exit | Result |
| --- | --- | --- |
| `helper` (bare) | `0` | normalizes to **`"pipe": "beta.helper"`** — the non-exported pipe, reached |
| `beta.helper` (qualified) | `1` | `Pipe 'beta.helper' referenced in pipe.run_flow.steps[0].pipe (domain 'alpha') is not exported by domain 'beta'. Add it to [exports.beta] pipes in METHODS.toml.` |

`[exports]` is unenforceable through the one reference form that is exempt from checking it. That is not a convenience the corpus happens to rely on; it is a hole, and it exists precisely because the resolver and the visibility checker read the same sentence differently.

The same page's § *Conflict Rules* carries the second casualty:

> | Different domains (same package) | Same concept or pipe code | No conflict — different namespaces. |

Crate-wide resolution converts that blessed no-conflict case into an ambiguity error. Two domains reusing a code — explicitly allowed by the standard — becomes a load failure the moment anything names it bare:

```sh
( cd "$DEMOS/ambiguous" && pipelex resolve . )
```

```
exit=1
Cannot resolve — the library is invalid:
Error validating pipe 'run_flow' dependency pipe 'summarize' because of: Ambiguous pipe code
'summarize' found in domains: ['alpha', 'beta']. Use domain-qualified ref.
```

Under the standard that bundle loads: `alpha.run_flow` names a bare `summarize`, `alpha` declares one, the search stops there. The error is not "the author was ambiguous" — the author was not; the resolver made them ambiguous by widening the search past the point where the standard stops it.

And the fall-through itself, for completeness:

```sh
( cd "$DEMOS/fallthrough" && pipelex resolve . )   # exit 0, step normalizes to "beta.present"
```

Three demos, three rows of the divergence table, all reproducible in about ten seconds.

### Re-measured after the pipe-side fix

Same three closures, same commands, on the fixed tree. Every prediction in this section held:

| Closure | Before | After |
| --- | --- | --- |
| `export-bypass` | exit `0`, bare `helper` reached the non-exported `beta.helper` | exit `1` — **the hole is closed**; the bare form no longer reaches another domain, so `[exports]` is enforceable through every reference form |
| `fallthrough` | exit `0`, step normalized to `beta.present` | exit `1`, naming the ref that was tried and suggesting the qualified spelling |
| `ambiguous` | exit `1`, `Ambiguous pipe code 'summarize' found in domains: ['alpha', 'beta']` | exit `0`, normalizes to **`alpha.summarize`** — the standard's answer. Two domains reusing a code is a no-conflict case again |

`export-bypass-control` is unchanged (exit `1`, the export error) — as it must be: that arm never depended on the resolver.

The `fallthrough` and `export-bypass` failures both read:

```
Pipe 'alpha.run_flow' references 'alpha.present', which does not exist. A bare pipe reference
resolves inside its own domain, so 'present' was read as 'alpha.present'. Referencing a pipe in
another domain requires writing that domain out. 'present' is declared elsewhere in this library —
did you mean 'beta.present'?
```

The suggestion comes from a crate-wide scan that runs **only** on the failure path. It suggests a spelling to a human; it never resolves a reference. Wiring it into a lookup would restore the bypass this section exists to document.

## 4. The same divergence is still live for concepts — and that reader is separately broken

`probes/concept-lookup-matrix.py` builds a two-domain library in memory and asks for a bare code under each shape of `search_domain_codes`. Measured output, verbatim:

| Library | `search_domain_codes` | Result |
| --- | --- | --- |
| `alpha.Memo` + `beta.Memo` | `None` | `ConceptLibraryConceptNotFoundError: Multiple concepts found for 'Memo'` |
| `beta.Memo` only | `None` | resolved **`beta.Memo`** — fall-through, from any domain |
| `alpha.Memo` + `beta.Memo` | `["alpha", "beta"]` | `ConceptLibraryConceptNotFoundError: Multiple concepts found for 'Memo'` |
| `beta.Memo` only | `["alpha", "beta"]` | `ConceptLibraryError: Concept 'alpha.Memo' not found in the library` |
| `beta.Memo` only | `["beta", "alpha"]` | `ConceptLibraryError: Concept 'alpha.Memo' not found in the library` |
| `alpha.Memo` + `beta.Memo` | `["alpha"]` | resolved `alpha.Memo` |

Three things fall out of that table, and the last two are defects nobody has filed:

1. **Rows 1–2 are the pipe divergence, verbatim, for concepts.** Fall-through where the standard errors; an ambiguity raise where the standard quietly succeeds. Meanwhile `_qualify_concept_ref` in the normalizer answers the *same authored text* the standard's way — confirm with `( cd "$DEMOS/concept-collision" && pipelex resolve . )`, which qualifies `alpha`'s bare `Note` to `alpha.Note` and `beta`'s to `beta.Note` and exits 0. Two readers, one fact, disagreeing — the exact defect class the parity track exists to remove, still open one file over from where it was closed for pipes.

2. **Rows 4–5: a multi-domain search list cannot survive a domain that lacks the code.** The loop at `concept_library.py:212-216` calls `get_required_concept`, which *raises* (`concept_library.py:164-166`) rather than returning `None`, so the walrus `if found_concept := …` never sees a falsy value — the first miss escapes the method. Worse, it escapes as `ConceptLibraryError`, and `ConceptLibraryError` is **not** a subclass of the `ConceptLibraryConceptNotFoundError` that every caller in `pipelex/core/stuffs/stuff_factory.py` catches (`pipelex/libraries/concept/exceptions.py` extends `LibraryLoadingError`; `pipelex/core/concepts/exceptions.py:37` extends `PipelexError` — sibling branches). So the error bypasses the handler that exists to contextualize it.

3. **Row 3 makes the deliberate ordering at `pipelex/pipeline/pipeline_run_setup.py:202-204` dead code.** That code inserts the running pipe's domain at position `0` so it wins; the loop then collects *all* matches and raises on `len > 1` before `found_concepts[0]` is ever returned. The own-domain preference it was written to express cannot fire.

**How live is (2) and (3)?** Latent, not live, today: `pipeline_run_setup.py:202-204` produces a single-element list, and no production call site passes a longer one (`grep -rn "search_domain_codes=\[" pipelex tests` finds only test call sites). That is worth stating plainly rather than dressing up — but it also means the multi-domain list is unusable the moment anyone reaches for it, and the standard's rule is exactly what makes the whole `search_domain_codes` parameter unnecessary.

**One thing to confirm rather than assume:** `search_domain_codes` is fixed once from the *entry* pipe's domain and carried on the runner (`pipelex/pipeline/runner.py:115-126`, `:226`). Whether a sub-pipe in another domain can reach a concept-shaping path with the entry domain in hand — and therefore fail to resolve its own bare concept ref — was not established here. It is a good first question for whoever picks this up.

## 5. The corpus — which direction is actually expensive

> **Superseded and widened (2026-08-11).** The scan below passes a hardcoded list of ten sibling repos, which turns out to reach under a fifth of the bundles outside this repo. Enumerating the workspace instead multiplies the corpus several times over and finds a **second** breaking reference, in `cocode` — a shipped CLI, not a samples directory. The numbers in this section remain accurate *for the roots it scanned*; read [corpus-measurement.md](corpus-measurement.md) for the current figures, what inflates them, and the reproduction command.

The deferred note's decisive reason was migration cost: *"Every `.mthds` in the wild that leans on cross-domain bare resolution stops loading."* That is the claim the probe was written to check.

`probes/classify-bare-refs.py` reads TOML and nothing else — no `pipelex` import, no library load — so it classifies what the corpus **asks for**, independent of what any resolver does with it. For each merge unit it builds `code -> {domains that declare it}` and sorts every bare in-body reference into four buckets.

```sh
python wip/pipe-refs/probes/classify-bare-refs.py .
python wip/pipe-refs/probes/classify-bare-refs.py \
    ../pipelex-cookbook ../pipelex-starter-python ../hub ../mthds ../pipelex-app \
    ../pipelex-api ../mthds-js ../pipelex-transport ../conformance ../pipelex-platform
```

| | this repo | every other `.mthds` tree in the workspace |
| --- | --- | --- |
| bundles read | 124 | 90 |
| merge units | 57 | 36 |
| **bare in-body pipe refs** | **142** | **158** |
| `own-only` — the referring domain declares it, nobody else. Standard and runtime agree | 136 | 153 |
| `sibling-only` — ONLY another domain declares it. Standard: error. Runtime: resolves | **0** | **1** |
| `both` — the referring domain *and* another declare it. Standard: the own one. Runtime: **raises** | 6 | 1 |
| `nowhere` — nobody declares it. Both error | 0 | 3 |
| **bare in-body concept refs** | **283** | **367** |
| `own-only` | 255 | 341 |
| `sibling-only` | **0** | **0** |
| `both` | 27 | 22 |
| `nowhere` | 1 | 4 |

**One bare pipe reference out of 300 leans on cross-domain resolution**, and it is `pipelex-cookbook/examples/wip/advisory_board/bundle.mthds` — `advisory_orchestrator.master_advisory_orchestrator` naming a bare `present_as_markdown` that only the `presentation` domain declares. It is fixed by writing `presentation.present_as_markdown`. **Zero** bare *concept* references lean on it, anywhere.

That is the entire migration cost of tightening, across every `.mthds` either repo can see. The cost argument that carried the deferral does not survive contact with the corpus.

**What this measurement does not cover — read before quoting it.**

- **A directory is not always a merge unit.** The probe treats a package (a tree with `METHODS.toml`) as one unit and otherwise groups by containing directory, which is how a `-L <dir>` load behaves. Test-fixture directories whose bundles are loaded *one at a time* are therefore over-grouped: most of the `both` rows are fixture pairs that never actually meet in one library, so the `both` column is an upper bound on "would start working", not a count of live breakage. **The `sibling-only` figure is the robust one.** Grouping is not monotone in general — a coarser unit can promote a `nowhere` ref into `sibling-only` — but every `nowhere` ref in the corpus is a *deliberately invalid* fixture (`missing_pipe_ref.do_two_steps -> 'second_step_missing'`, in three copies; the probe prints them), so none of them can become a real cross-domain reference under any grouping. One is one.
- **In-body references only.** `main_pipe` and `[exports]` entries are not classified.
- **Bare concept refs exclude natives**, which take priority by the standard's own step 1.
- **Customer bundles are out of reach by construction.** But "one in 300, in an `examples/wip/` directory" is a very different prior from "every `.mthds` in the wild".
- **Do not materialize the demos inside this tree.** `make-demos.sh` writes to a `mktemp` directory by default for exactly this reason — the demo bundles are pathological, and dropping them into the repo would move the counts above.

## 6. Answering the deferral's three reasons

> **1. It is a behavior change to the language, not to a reader.**

True, and the measurement is what sizes it: one reference, in an examples directory. Worth adding that the *current* state is also a behaviour change to the language — an undeclared one, made by a resolver rather than by a spec edit, which took away two guarantees (§3) the standard still advertises.

> **2. It is cross-repo.**

True, and it stays cross-repo whichever way it settles. That is an argument about how to land it, not about which way.

> **3. The direction of the fix is genuinely open […] cross-domain bare resolution inside a single crate is convenient and has evidently been relied on.**

"Evidently been relied on" is the assumption the numbers contradict: one reference, in `examples/wip/`. And loosening the standard is not a one-line edit either — it means deleting the bare-reference exemption from § *Visibility Rules*, rewriting the § *Conflict Rules* row for different domains in one package, and answering what `[exports]` is for once bare refs route around it (§3). Of the three positions in play — the standard, this runtime's pipe readers, this runtime's concept readers — the standard is the only one that is internally consistent today.

## 7. Proposed shape of the fix

A proposal, not a decision. The deferred note's closing rule — *"Do not fix one reader and not the other"* — is right and extends one step further than it was applied: not one reader and not the other, and **not pipes and not concepts**.

**In this repository:**

- `PipeLibrary.get_optional_pipe` takes the caller's domain and stops at it: own bundle → own domain → not found. The permissive crate-wide search is arguably still right for *entry-point* lookups (a user typing `pipelex run my_pipe` with no domain in hand); if so, keep it there and make it an explicit, separately-named affordance rather than the resolution rule for in-body references. **Deciding that split is the first design question.**
- `ConceptLibrary.get_required_concept_from_concept_ref_or_code` does the same, which also deletes the `search_domain_codes` machinery's reason to exist and takes the two defects in §4 with it.
- `_qualify_pipe_ref` in `crate_normalization.py` reverts to owner-domain qualification — becoming the twin of `_qualify_concept_ref` sitting beside it — so the two readers agree by moving the one that is wrong about the standard, rather than the one that is right.
- **The real work is the 63 call sites** (`grep -rn "get_optional_pipe\|get_required_pipe(" pipelex | grep -v "def get_"`), which today pass a bare code with no domain. Most are inside a `Pipe*` instance and so already hold `self.domain_code` (`pipelex/pipe_machinery/pipe_abstract.py:94`), but `pipelex/interpreter_hub.py:346-350` is the funnel and its signature has to change. Scope this before committing to the change.

**Tests that pin today's behaviour and must flip** (they are correct tests of the current rule; they become tests of the new one):

- `tests/unit/pipelex/libraries/test_crate_normalization.py::test_bare_cross_domain_pipe_refs_resolve_to_the_declaring_domain` — its docstring states the fall-through as the intended contract.
- `tests/unit/pipelex/libraries/test_pipe_library_lookup.py::test_bare_code_ambiguous_raises` and `::test_bare_code_unambiguous` — same, for the library.
- `pipelex/pipeline/fixes/fix_loop.py:401` carries a comment describing the ambiguity raise as a fact about the library; check whether the surrounding logic depends on it.

**Outside this repository** (each is somebody else's merge, so land them in a coordinated set):

- `mthds/` — **no normative change**. One additive clarification is worth making, because this round is evidence it is needed: say at § *Resolution Order for Bare Pipe References* that no-fall-through is what makes `[exports]` enforceable, so the next reader does not take it for a lookup convenience.
- `conformance/` — the four rows of §5's table as executable cases (own-only resolves; sibling-only errors; both resolves to the referring domain's own; nowhere errors), plus the export-bypass case from §3, which is the one nobody would think to write without the visibility argument.
- `pipelex-cookbook` — qualify one reference in `examples/wip/advisory_board/bundle.mthds`.

## 8. What to verify before building

The claims above are measured, but a plan should not rest on someone else's measurements. Re-run them — `probes/` is two scripts and a shell generator, and the whole set takes under a minute — and settle these before writing code:

1. **Does the export bypass reproduce?** It is the load-bearing claim. If it does not, §3 collapses and the question really is open.
2. **Is the entry-point lookup genuinely a different concern from in-body resolution?** If yes, the fix is two functions rather than one, and the corpus numbers in §5 (which count *in-body* references only) are the right ones to reason from. If no, `pipelex run <bare code>` gets stricter and that is a UX change worth naming.
3. **Can a sub-pipe in a non-entry domain reach a concept-shaping path?** (§4, last paragraph.) It decides whether the concept side has a live bug or only a latent one.
4. **What does threading the caller's domain through `interpreter_hub` actually cost?** 63 call sites is a count, not a scope. Some are validation walks, some are hot-path execution; they may not all have a caller domain to offer.
5. **Are there `.mthds` consumers outside this workspace** — customer bundles, published packages — that the §5 corpus cannot see, and is there any way to sample them?

---

## Reproducing everything in this document

```sh
# corpus classification (§5)
python wip/pipe-refs/probes/classify-bare-refs.py .
python wip/pipe-refs/probes/classify-bare-refs.py ../pipelex-cookbook ../pipelex-starter-python \
    ../hub ../mthds ../pipelex-app ../pipelex-api ../mthds-js ../pipelex-transport \
    ../conformance ../pipelex-platform

# concept lookup matrix (§4)
.venv/bin/python wip/pipe-refs/probes/concept-lookup-matrix.py   # needs the venv: this probe imports pipelex

# the five demo closures (§3, §4)
DEMOS=$(./wip/pipe-refs/probes/make-demos.sh | tail -1)
for case in ambiguous fallthrough export-bypass export-bypass-control concept-collision; do
    printf '\n===== %s =====\n' "$case"
    ( cd "$DEMOS/$case" && pipelex resolve . )
done
```

Run these from the repository root with this checkout's environment active, so that `python` and `pipelex` are the ones installed from this tree (`.venv/bin/python`, `.venv/bin/pipelex`) rather than whatever is on `PATH` — the point of every number here is that it describes *this* code. Set `PIPELEX_NO_DECK_NOTICE=1` to silence the model-deck banner; none of these commands needs credentials or reaches an inference backend.

## See also

- [`../parity/bare-pipe-ref-spec-divergence.md`](../parity/bare-pipe-ref-spec-divergence.md) — the deferral this document answers.
- [`../parity/d1-domain-hint-deferred.md`](../parity/d1-domain-hint-deferred.md) — the narrower `domain_hint` question. Compliance subsumes it: if bare refs never leave their domain, cross-domain ambiguity cannot arise.
- [`../parity/deferred-review-observations.md`](../parity/deferred-review-observations.md) § 4 — the ordering dependency noted there (settle the resolution rule before writing the spec paragraph) is the reason §7 puts the `mthds/` edit last.
