# Configuration Internals (defaults and overrides)

This page is for **contributors**: it explains where Pipelex defaults live, how configuration is merged at runtime, and where to change the behavior in code.

For the user-facing configuration guide, see [Configuration Overview](../configuration/index.md).

## Mental model (for contributors)

Pipelex configuration is merged in layers:

- **Shipped defaults**: maintained by the Pipelex project and used as the baseline by the installed package.
- **Global config** (`~/.pipelex/`): machine-wide settings for a developer, applied to every project on the machine.
- **Project config** (`{project_root}/.pipelex/`): per-project settings, edited by teams using Pipelex.
- **Override files** at each level (`pipelex_local.toml`, `pipelex_{environment}.toml`, `pipelex_{run_mode}.toml`, `pipelex_override.toml`, `pipelex_temporary_override.toml`): optional, typically gitignored, used for personal or ephemeral tweaks.

The key idea: global personal preferences layer **under** project-specific settings — both are loaded, and project values win on collisions. Nothing in `~/.pipelex/` is shadowed by the mere existence of a project `.pipelex/`.

## Where defaults live (Pipelex repository)

- **Default values** (baseline): `pipelex/pipelex.toml`, shipped inside the package
- **User-facing templates** copied into `.pipelex/` by the init flow: `pipelex/kit/configs/…`

## Merge order (runtime)

The configuration loading/merging behavior is implemented in `pipelex/system/configuration/config_loader.py`. Files are deep-merged via `load_toml_from_path_and_merge_with_overrides`; the later a file appears in the load list, the higher its precedence per leaf key.

Load order:

1. **Package defaults** — `pipelex/pipelex.toml` shipped with the installed package.
2. **Global base** — `~/.pipelex/pipelex.toml`.
3. **Global override sequence** — from `~/.pipelex/`, in this order:
    1. `pipelex_local.toml`
    2. `pipelex_{environment}.toml`
    3. `pipelex_{run_mode}.toml` *(see unit-test special case below)*
    4. `pipelex_override.toml`
    5. `pipelex_temporary_override.toml`
4. **Project base** — `{project_root}/.pipelex/pipelex.toml`, if a project `.pipelex/` exists and is distinct from `~/.pipelex/`.
5. **Project override sequence** — same five files as step 3, read from `{project_root}/.pipelex/`, if the project dir is distinct from the global dir.
6. **Programmatic `extra_overrides`** passed into `ConfigLoader.load_config()` (if any).

!!! note "Unit-test special case"
    When `runtime_manager.is_unit_testing` is true, the `pipelex_{run_mode}.toml` entry is sourced exclusively from `./tests/pipelex_{run_mode}.toml` (e.g. `tests/pipelex_unit_test.toml`). Global and project run_mode files are not loaded, keeping test runs hermetic from machine-wide overrides.

## Where to change things in code

- **Config merge logic**: `pipelex/system/configuration/config_loader.py`
- **Override file sequences**: `ConfigLoader._override_files_for_dir` and `ConfigLoader._plugin_override_files_for_dir` in that same file

## Contributor guidelines for config changes

- If you change **defaults**, update `pipelex/pipelex.toml` (and consider whether templates in `pipelex/kit/configs/…` should also be updated).
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

