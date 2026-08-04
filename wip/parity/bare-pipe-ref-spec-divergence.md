# Bare pipe references resolve across domains, and the MTHDS spec says they must not

**Status:** deferred, deliberately. Surfaced by a review bot against the D-1 note on PR #1085; verified and recorded here rather than fixed. This is a **language decision with cross-repo consequences**, not a parity fix.

## The divergence

`mthds/docs/spec/namespace-resolution.md` § *Resolution Order for Bare Pipe References* is explicit:

> 1. **Current bundle** — check pipes declared in the same `.mthds` file.
> 2. **Same domain, other bundles** — if the bundle is part of a package, check pipes in other bundles that declare the same domain.
> 3. **Error** — if not found, the reference is invalid.
>
> Bare pipe references do NOT fall through to other domains or other packages.

The runtime does fall through. `PipeLibrary.get_optional_pipe` (`pipelex/libraries/pipe/pipe_library.py`), step 3, is commented *"Bare code fallback — search across domains"* and matches on `val.code == pipe_code` across every non-cross-package entry, ignoring the caller's domain entirely:

| bare ref `foo` used from domain `A` | spec | runtime today |
| --- | --- | --- |
| only `A.foo` exists | `A.foo` | `A.foo` |
| only `B.foo` exists | **error** — no fall-through | `B.foo` |
| both exist | **error** — never reached, `A.foo` wins at step 1 | raises `PipeLibraryError` (ambiguous) |
| neither | error | `None` → `PipeNotFoundError` |

Row 2 is the divergence. Row 3 diverges in its *reason* rather than its outcome — both error, but the spec errors because it never left domain `A`, while the runtime errors because it searched everywhere and found two.

## Why the parity fix mirrored the runtime rather than the spec

Deliberately, and it would be a mistake to "correct" it in isolation. Phase 1's 1.1 made the crate normalizer resolve bare pipe refs the way `get_optional_pipe` does — crate-wide — because the track's entire purpose is that two readers of one authored fact agree. Making the *normalizer* spec-compliant while the runtime stayed permissive would have manufactured a fresh disagreement of exactly the kind being removed: a library that normalizes to an error but runs fine, or vice versa.

So the landed state is coherent: **both readers agree, and both are more permissive than the spec.** That is a strictly better position than where the track started, and it is the correct stopping point for a parity change.

See [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md) for the separate, narrower question it raises (whether `get_optional_pipe` should grow a `domain_hint` and prefer the caller's domain on ambiguity). Note the two pull in opposite directions and should be settled together: `domain_hint` makes the runtime *prefer* the own domain on ambiguity, while spec compliance makes it *never leave* the own domain at all. Spec compliance subsumes the `domain_hint` question — if bare refs never fall through, ambiguity across domains cannot arise.

## Why this is not being fixed here

Three reasons, and the third is decisive.

1. **It is a behavior change to the language, not to a reader.** Every `.mthds` in the wild that leans on cross-domain bare resolution stops loading. That is the opposite of a zero-behavior-change parity fix.
2. **It is cross-repo.** The rule lives in `mthds/` (the standard) and is implemented in `pipelex/`; `conformance/` would need the case, and any bundle in `pipelex-cookbook/`, the demo repos or the hub that relies on the fall-through would need qualifying. A one-line resolver change does not scope it.
3. **The direction of the fix is genuinely open, and it is not this track's call.** Either the runtime tightens to the spec, or the spec loosens to describe what every implementation actually does. The second is not obviously wrong — cross-domain bare resolution inside a single crate is convenient and has evidently been relied on. Picking one is a language-owner decision.

## What to do with it

Raise it with whoever owns the MTHDS spec, together with D-1. Whichever way it settles, the change lands in one PR carrying: the resolver, the crate normalizer (they must move together — that is this track's whole lesson), the spec page, a `conformance/` case, and the sweep of any bundle that relied on the old behavior.

**Do not fix one reader and not the other.** That is the defect class this entire track exists to remove, and it would be an unusually ironic way to reintroduce it.
