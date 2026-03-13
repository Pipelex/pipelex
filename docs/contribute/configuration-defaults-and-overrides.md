# Configuration Internals (defaults and overrides)

This page is for **contributors**: it explains where Pipelex defaults live, how configuration is merged at runtime, and where to change the behavior in code.

For the user-facing configuration guide, see [Configuration Overview](../configuration/index.md).

## Mental model (for contributors)

Pipelex configuration is merged in layers:

- **Shipped defaults**: maintained by the Pipelex project and used as the baseline by the installed package.
- **Project overrides**: created in `.pipelex/` by `pipelex init …` and edited by projects that use Pipelex.
- **Root override files** (advanced): optional files for machine/env/run-mode/super overrides.

The key idea: client projects typically edit **`.pipelex/`**, while the Pipelex repository holds the **default values** used as a starting point.

## Where defaults live (Pipelex repository)

- **Default values** (baseline): repo root `pipelex.toml`
- **User-facing templates** copied into `.pipelex/` by the init flow: `pipelex/kit/configs/…`

## Merge order (runtime)

The configuration loading/merging behavior is implemented in `pipelex/system/configuration/config_loader.py`.

At a high level, the load order is:

1. **Pipelex base defaults** (from the installed package)
2. **Project config** from `.pipelex/pipelex.toml` (when running in a client project)
3. **Root overrides** (optional), in this order:
   1. `pipelex_local.toml`
   2. `pipelex_{environment}.toml`
   3. `pipelex_{run_mode}.toml`
   4. `pipelex_override.toml`

!!! note "Unit test special case"
    When unit testing, run-mode overrides may be loaded from `tests/pipelex_{run_mode}.toml` (example: `tests/pipelex_unit_test.toml`).

## Where to change things in code

- **Config merge logic**: `pipelex/system/configuration/config_loader.py`
- **Override lists** (`local` / `super`): `pipelex/system/configuration/config_root.py`

## Contributor guidelines for config changes

- If you change **defaults**, update the repo root `pipelex.toml` (and consider whether templates in `pipelex/kit/configs/…` should also be updated).
- If you change **templates**, keep them user-focused and stable; avoid adding internal-only details.
- If you change **merge order or override semantics**, treat it as a potentially breaking change and document it (changelog + migration notes if needed).

---

## Test Profile Configuration

The test profile system controls which AI models are included in parametrized tests. This is separate from the main Pipelex configuration.

### Files

| File | Purpose | Tracked |
|------|---------|---------|
| `.pipelex-dev/test_profiles.toml` | Base profiles and model collections | Yes |
| `.pipelex-dev/test_profiles_override.toml` | Local customizations | No (gitignored) |

### How it works

1. Collections define reusable lists of models organized by provider
2. Profiles reference collections or specify models directly
3. The preprocessing command resolves references and generates fixture files

### Key code locations

- **Profile loading & merging**: `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py`
- **Generated fixtures**: `tests/integration/pipelex/fixtures/_generated_model_sets.py`

### Common tasks

```bash
# Regenerate fixtures with default (dev) profile
make regenerate-test-models

# Use a specific profile
make regenerate-test-models TEST_PROFILE=full
```

For full documentation, see [Test Profile Configuration](../under-the-hood/test-profile-configuration.md).

