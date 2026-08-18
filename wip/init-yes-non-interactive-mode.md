# `pipelex init` has no non-interactive mode, and it costs downstream repos their config hygiene

**Status:** Follow-up TODO, raised from the cocode v0.10.0 release (2026-08-18). Not a regression — `init` has never had the flag. Bounded, and `pipelex migrate` already ships the exact shape the fix needs.

## The gap

As of pipelex 0.46.1, `pipelex init --help` offers the `focus` argument (`all|agreement|config|credentials|inference|routing|telemetry`) and exactly two options: `--local / -l` and `--help`. There is no `--yes`, no `--skip-confirmation`, no non-interactive path of any kind.

Its sibling on the same CLI already has one. `pipelex migrate --help` offers `--dry-run` ("Report what would change and write nothing") and `--yes / -y` ("Apply without the interactive confirmation"). The vocabulary, the precedent and the user expectation all exist already; `init` simply never got it.

## Why this matters beyond ergonomics

A CI runner cannot call `pipelex init`. So any repo whose test suite boots Pipelex has to get a `.pipelex/` config into place some other way, and with no non-interactive init the only remaining way is to commit one into the repo.

cocode hit this concretely and the workaround is still load-bearing there. On 2026-06-05, inside its `release/v0.7.0` branch:

- 08:55 `1dd8831` — de-vendored `.pipelex/` entirely, on the stated reasoning "uses your global config unless you create a specific config"
- 08:56 `8ab1904` — added `.pipelex/` to `.gitignore`, the correct companion to that decision
- 12:52 `6c6c689` — "re-vendored config for CI": the files came back, forced past the ignore rule with `git add -f`, because CI has neither a global `~/.pipelex/` nor an init step
- 13:05 — squash-merged as `6b9b072`, which is why the merged history shows only a confusing net result rather than this sequence

As of 2026-08-18 cocode still force-tracks its `.pipelex/` directory past its own `.gitignore`, so that ignore line has been contradicting reality ever since. The practical cost is that every pipelex config-schema change lands in a cocode release diff as a wall of vendored TOML: the 0.46 config-root reshape plus the `prompting_target` removal dragged cocode's whole vendored backend directory into its v0.10.0 release. Note that `--disable-inference` does not sidestep any of this — it swaps in mock inference, it does not skip initialization.

## What the fix looks like

Give `init` the same treatment `migrate` already has, or at minimum `--yes`:

- `pipelex init --yes --local` writes a project `.pipelex/` with every prompt taking its default and no TTY required.
- CI runs that as a step ahead of its test target, and the downstream repo deletes its vendored config and keeps the honest `.gitignore` line it wrote in the first place.

Auto-detecting a non-TTY or `CI=true` environment is the obvious alternative, but an explicit flag is the safer contract: an `init` that silently writes files because it could not find a terminal is a worse surprise than one that refuses.

Recorded when this was last examined, against an earlier pipelex — **re-verify against 0.46.x before scoping**: `init_cmd` already accepted a `skip_confirmation` argument, and every init prompt already carried a usable `default=`. That is what made this look like wiring rather than a redesign.

## Downstream unblock

Once this ships and cocode re-pins to it:

- add `pipelex init --yes --local` to cocode's `tests-check.yml`, ahead of `make gha-tests`
- `git rm -r --cached .pipelex/` in cocode and let the existing ignore rule finally mean what it says
- cocode's `tests/conftest.py` boots Pipelex and needs config present; the specifics of that gate live in cocode's repo, not here
