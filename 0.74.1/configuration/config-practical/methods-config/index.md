# Methods Configuration

The `MethodsConfig` class controls the behavior of installed and fetched method packages.

## Configuration Options

```python
class MethodsConfig(ConfigModel):
    fetch_on_miss: bool
```

### Fields

- `fetch_on_miss`: When a bundle references another method by address (`github.com/...->domain.pipe`) and no installed method matches, fetch the package by address and install it into `~/.mthds/methods/` so the load can proceed. When disabled, such a miss raises a diagnostic naming the address and how to install the method manually, and the network is never touched at load time.

## Example Configuration

```toml
[interpreter.methods]
fetch_on_miss = true
```

## Environment Variable Override

The `PIPELEX_METHODS_FETCH_ON_MISS` environment variable overrides the config when set: `1`/`true`/`yes`/`on` enables fetching, `0`/`false`/`no`/`off` disables it. An unrecognized value is warned about and ignored in favor of the config.

```bash
# Force-disable network fetches at load time for this shell
export PIPELEX_METHODS_FETCH_ON_MISS=0
```

## When to Disable It

- Offline or air-gapped environments, where a fetch could only hang or fail.
- Deployments that must never pull code from the network at load time.
- Reproducibility-sensitive runs where every dependency must be pre-installed and reviewed.

## Related Documentation

- [Packages](../../building-methods/packages.md) — Cross-package references and include by address
- [Run a Method by Address](../../tools/cli/run-by-address.md) — The reference grammar, bounds, and provenance
