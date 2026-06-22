# Follow-up: the plugin-API version gate guards nothing — build real version gating (semver)

Surfaced while reconciling the orchestration-mode / delivery split branch against the merged `#1000` (`refactor: split execution_mode into orchestration_mode + DeliveryMode`). The question was whether `#1000`'s breaking change to the orchestrator contract warranted bumping `PLUGIN_API_VERSION` from 2 → 3. Investigating that turned up a deeper problem: **the version gate, as wired today, cannot reject any plugin — it is purely documentary.** This is the task to fix it.

This is the implementation gap behind synthesis point **#13** in [`README.md`](README.md) ("Version the core↔plugin contract … make the contract break *visible*"). The mechanism exists; it just doesn't do what #13 promises.

## The finding: the gate is toothless

The contract is a single coarse integer with an exact-match gate:

- `pipelex/plugins/contract.py:14` — `PLUGIN_API_VERSION: int = 2`. A plugin declares the version it targets via the `targets_api: int` field (`contract.py:35`).
- `pipelex/plugins/discovery.py:100` — the gate:

  ```python
  targets_api = getattr(plugin, "targets_api", None)
  if targets_api != PLUGIN_API_VERSION:
      raise PluginApiVersionMismatchError(...)
  registrar.begin_plugin(name=plugin.name, origin=origin, targets_api=PLUGIN_API_VERSION)
  ```

The mechanism can never fire, because **every plugin sets `targets_api = PLUGIN_API_VERSION` by importing the constant** — built-ins (`openai_plugin.py`, `anthropic_plugin.py`, `direct_plugin.py`, …) *and* both external orchestrator plugins:

- `pipelex-mistralai-workflows/pipelex_mistralai_workflows/mistral_plugin.py` — `from pipelex.plugins.contract import PLUGIN_API_VERSION` / `targets_api = PLUGIN_API_VERSION`.
- `pipelex-temporal/pipelex_temporal/temporal_plugin.py` — same pattern.

So a plugin's declared `targets_api` *always equals the core it is installed against*. `targets_api != PLUGIN_API_VERSION` is structurally unreachable for any cooperative plugin, no matter what the constant's value is. Nothing in the workspace pins a literal `targets_api` (a `grep -rE 'targets_api\s*=\s*[0-9]'` over every repo returns nothing). And note `discovery.py:105` even *records* the core's `PLUGIN_API_VERSION`, not the plugin's declared value — the system assumes the two are identical by construction.

## Worked proof that this already let a breaking change through silently

`#1000` reshaped the orchestrator SPI in ways that are each a hard break for a plugin built against the prior contract:

- `OrchestratorProtocol.run` gained a required `delivery: DeliveryMode` keyword (no default), and the bridge passes it **unconditionally** (`pipelex/runtime_bridge/bridge.py:102`) → a prior `run` raises `TypeError` at dispatch.
- A new required `supports_fire_and_forget: bool` attribute, read with **no getattr default** (`bridge.py:178`) → a prior orchestrator raises `AttributeError` at `/start`.
- `pipelex/runtime_bridge/execution_mode.py` (defining `PipelexExecutionMode`) was **deleted**; the registry is re-keyed by the open `OrchestrationMode` string token → a prior plugin importing `PipelexExecutionMode` fails at import.

That is unambiguously a breaking SPI change — yet `#1000` shipped with `PLUGIN_API_VERSION` still at **2**, and nothing flagged it. It couldn't: the two external orchestrator plugins were migrated to the new contract in lockstep and re-import the (still-`2`) constant, so the gate stayed satisfied. The version number now labels two incompatible contracts (pre- and post-`#1000`), which is exactly the silent-incompatibility footgun #13 says the gate exists to prevent.

## Why it's harmless *today* but must be fixed before externalization

No published, out-of-tree, third-party plugin exists, and no version of the plugin API has shipped — so there is no real artifact pinned to an old contract for the gate to protect. The bump-to-3 vs stay-at-2 question is therefore moot in practice (which is why the reconciliation just dropped the inert bump and matched origin).

It stops being moot the moment a third party publishes a plugin against a *released* pipelex and pins the version it built against. At that point the current design fails them twice: a plugin that imports the constant still can't detect skew, and a plugin that pins a literal hits an exact-match `!=` that also rejects *compatible* (additive) core versions.

## The proper design (semver)

Two distinct defects to fix — neither alone is sufficient:

1. **Plugins must pin the version they were built against as a literal, not `= PLUGIN_API_VERSION`.** Importing the constant is what makes the declared version auto-track core and the gate inert. The declared value has to be a fact about the plugin's *source* (the contract it was coded against), frozen at author time — not a value re-read from whatever core happens to be installed.

2. **Replace the exact-match gate with a semver compatibility rule.** Even with literals, `!=` is too brittle — it rejects a plugin built against an older *compatible* core.

Concretely:

- Core publishes the plugin-API version as `MAJOR.MINOR` (PATCH irrelevant to the contract). **MAJOR** bumps on a breaking change — a removed/renamed SPI symbol, a changed required signature, a changed registry key type (i.e. exactly `#1000`). **MINOR** bumps on a backward-compatible addition — e.g. v2's optional `add_http_error_mapper` was purely additive and would have been a MINOR bump that required no existing plugin to change.
- A plugin declares `built_against = (MAJOR, MINOR)` as a literal.
- Compatibility: `plugin.major == core.major AND plugin.minor <= core.minor`. Same major ⇒ no breaking change since the plugin was built; `minor <=` core ⇒ every capability the plugin relies on exists in the installed core. Reject on a major mismatch, **loud**, naming both versions and the remediation (rebuild against / upgrade to plugin API `N.x`) — that is the visible break #13 wants. (`PluginApiVersionMismatchError` already carries `targets_api` + `supported_api`; the message just needs to speak semver and name the fix.)
- Re-framed: `#1000` is a MAJOR bump `2.x → 3.0`; `pipelex-mistralai-workflows` and `pipelex-temporal` each declare `(3, 0)`; a stale third-party plugin pinned to `(2, x)` is cleanly rejected at boot with "rebuild against pipelex plugin API 3.x" instead of crashing at dispatch with a `TypeError`.

Optional refinement if needed later: let a plugin also declare a maximum supported major, so a plugin can advertise forward-compat across a range rather than a single built-against point. Start with built-against-min; add the range only if a real consumer needs it.

## Scope when this is picked up

- `pipelex/plugins/contract.py` — version constant → a `MAJOR.MINOR` pair (or a small `PluginApiVersion` value object) + the compatibility helper. Update the "bump this only on a breaking change" comment to define MAJOR vs MINOR.
- `pipelex/plugins/discovery.py:100` — gate calls the compatibility helper instead of `!=`; record the plugin's *declared* version, not core's.
- `pipelex/plugins/exceptions.py` — `PluginApiVersionMismatchError` message speaks semver and names the remediation.
- **Plugin authoring convention** — the real behavioral change: built-in and external plugins stop doing `targets_api = PLUGIN_API_VERSION` and pin a literal built-against version. Without this, no gate (semver or otherwise) has teeth. This is also a conformance-test opportunity: assert no plugin imports the constant for its declared version.
- Docs — `docs/under-the-hood/orchestrator-plugins.md` (the SPI/versioning section) and README #13.

## Status

Not started. Design task, deferred — no urgency while nothing is shipped, but it should land **before the first out-of-tree third-party plugin is published against a released pipelex**, since that is the first moment the gate is asked to do its job for real.
