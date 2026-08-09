# Bare pipe references resolve across domains, and the MTHDS spec says they must not

**Status:** deferred, deliberately. Surfaced by a review bot against the D-1 note on PR #1085; verified and recorded here rather than fixed. This is a **language decision with cross-repo consequences**, not a parity fix.

## The divergence

The MTHDS standard is explicit. **The spec is not in this repository** — it lives in the sibling `mthds/` repo at the workspace root (the open standard, published to mthds.ai), so a fresh `pipelex` clone cannot resolve the path below. The normative sentences are quoted verbatim here so the claim stays checkable without it; to re-verify against the source, read `docs/spec/namespace-resolution.md` § *Resolution Order for Bare Pipe References* in `mthds/`.

> 1. **Current bundle** — check pipes declared in the same `.mthds` file.
> 2. **Same domain, other bundles** — if the bundle is part of a package, check pipes in other bundles that declare the same domain.
> 3. **Error** — if not found, the reference is invalid.
>
> Bare pipe references do NOT fall through to other domains or other packages.

The runtime does fall through. `PipeLibrary.get_optional_pipe` (`pipelex/libraries/pipe/pipe_library.py`), step 3, is commented *"Bare code fallback — search across domains"* and matches on `val.code == pipe_code` across every non-cross-package entry, ignoring the caller's domain entirely:

| bare ref `foo` used from domain `A` | spec | runtime today | |
| --- | --- | --- | --- |
| only `A.foo` exists | `A.foo` | `A.foo` | agree |
| only `B.foo` exists | **error** — no fall-through | `B.foo` | **differ** |
| both exist | `A.foo` — found in the own domain at step 1/2, so the search stops before `B` | **raises** `PipeLibraryError` (ambiguous) | **differ** |
| neither | error | `None` → `PipeNotFoundError` | agree |

**Two rows diverge, and both diverge in outcome.** Row 2 is the fall-through the spec forbids. Row 3 is subtler and easy to get backwards: the spec never reaches an ambiguity at all, because it finds `A.foo` in the caller's own domain and stops — so where the spec quietly succeeds, the runtime raises. A working bundle under the spec is a hard error today.

Row 3 also settles the relationship to D-1: the answer the spec gives there — prefer the own domain — is exactly what a `domain_hint` would produce. Spec compliance therefore delivers D-1's outcome for the ambiguous case *and* closes row 2, which `domain_hint` alone would leave open.

## Why the parity fix mirrored the runtime rather than the spec

Deliberately, and it would be a mistake to "correct" it in isolation. Phase 1's 1.1 made the crate normalizer resolve bare pipe refs the way `get_optional_pipe` does — crate-wide — because the track's entire purpose is that two readers of one authored fact agree. Making the *normalizer* spec-compliant while the runtime stayed permissive would have manufactured a fresh disagreement of exactly the kind being removed: a library that normalizes to an error but runs fine, or vice versa.

So the landed state is coherent: **both readers agree with each other, and both disagree with the spec in the same two places.** That is a strictly better position than where the track started, and it is the correct stopping point for a parity change.

Note the disagreement does not run one way. On row 2 the runtime is *more permissive* than the spec (it resolves where the spec errors); on row 3 it is *stricter* (it raises where the spec quietly returns `A.foo`). "The runtime is looser than the standard" is the tempting one-line summary and it is wrong — worth knowing before anyone reasons about which direction a fix travels.

See [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md) for the narrower question this raises (whether `get_optional_pipe` should grow a `domain_hint` and prefer the caller's domain on ambiguity). **Spec compliance subsumes it**: if bare refs never leave their own domain, cross-domain ambiguity cannot arise, and row 3 resolves to `A.foo` — the same answer `domain_hint` was invented to produce. Settle them together, and settle the spec question first, because it decides whether `domain_hint` has anything left to do.

## Why this is not being fixed here

Three reasons, and the third is decisive.

1. **It is a behavior change to the language, not to a reader.** Every `.mthds` in the wild that leans on cross-domain bare resolution stops loading. That is the opposite of a zero-behavior-change parity fix.
2. **It is cross-repo.** The rule lives in `mthds/` (the standard) and is implemented in `pipelex/`; `conformance/` would need the case, and any bundle in `pipelex-cookbook/`, the demo repos or the hub that relies on the fall-through would need qualifying. A one-line resolver change does not scope it.
3. **The direction of the fix is genuinely open, and it is not this track's call.** Either the runtime tightens to the spec, or the spec loosens to describe what every implementation actually does. The second is not obviously wrong — cross-domain bare resolution inside a single crate is convenient and has evidently been relied on. Picking one is a language-owner decision.

## What to do with it

Raise it with whoever owns the MTHDS spec, together with D-1. Whichever way it settles, the change lands in one PR carrying: the resolver, the crate normalizer (they must move together — that is this track's whole lesson), the spec page, a `conformance/` case, and the sweep of any bundle that relied on the old behavior.

**Do not fix one reader and not the other.** That is the defect class this entire track exists to remove, and it would be an unusually ironic way to reintroduce it.
