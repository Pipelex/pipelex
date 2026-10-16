---
title: "The Error Registry"
description: "How Pipelex's error codes are authored in one public registry file, in the MTHDS registry format, and how its JSON snapshot, its typed Python and its documentation pages are generated and checked from it."
---

# The Error Registry

The MTHDS standard names every error a runner or a client can meet with a code, and publishes those codes as its core error registry. What the standard leaves to implementations, such as billing, organizations, the hosted catalog, Pipelex's storage, its own configuration and plugins, and the components it ships, Pipelex names with codes of its own under the `pipelex` extension prefix, which the core registry registers to Pipelex. This page describes how those codes are maintained.

## One source, three derived outputs

The Pipelex codes are authored in one public file, `pipelex/errors/registry/pipelex-error-registry.yaml`, in the [MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/). Each entry declares every member its code needs: its title, the domain whose actor must act, its retry verdict, the step for that actor and the step for any other reader, its typed parameters, the templates its sentences are written from, its HTTP status, and what its page says it means and what to do about it.

Everything else is generated from that file, and never edited by hand:

- `pipelex/errors/registry/pipelex-error-registry.json`, the registry's JSON snapshot. The `pipelex` package ships it, `load_pipelex_error_registry()` in `pipelex/errors/registry/registry_document.py` reads it into a typed model, and every release attaches it to the GitHub release as an asset.
- `pipelex/errors/registry/pipelex_codes.py`, the typed Python of the codes: a `PipelexErrorCode` member per code, and a closed, frozen parameters model per code, `PIPELEX_ERROR_PARAMS` mapping each code to its model.
- The documentation pages under `docs/errors/`: the [Error Codes](../errors/index.md) index and one page per code.

Regenerate them all after changing the source:

```bash
make generate-error-registry   # alias: make ger
```

The generator refuses to write anything from a source with a fault, and prints the faults. To check without writing, which is what the test suite does as well:

```bash
make check-error-registry      # alias: make cer
```

The test suite fails when any derived file is not what the generator writes, so a change to the source cannot land without its outputs.

### The registry's version

The source carries no version. The snapshot takes Pipelex's own version, the `[project].version` of `pyproject.toml`, so the number is written in one place and every release publishes the registry under the release's number. A version bump therefore leaves the snapshot and the index page stale until they are regenerated, which the test suite reports: run `make generate-error-registry` after bumping the version. The release workflow refuses to attach a snapshot whose version is not the release's.

The registry format writes a version as SemVer, while Pipelex's is a PEP 440 version, so a pre-release's number is written in its SemVer form: `0.88.0a1` becomes `0.88.0-a.1`, `0.88.0b2` becomes `0.88.0-b.2` and `0.88.0rc1` becomes `0.88.0-rc.1`, which SemVer orders as PEP 440 does, while a release's number, such as `0.88.0`, is written as it is. The generator and the release workflow's check both take the conversion from `pipelex/cli/dev_cli/commands/error_registry/registry_version.py`, which needs only the standard library so that the workflow runs it on a bare runner.

## The typed codes

Whoever raises a code builds its parameters with the model the registry generates, so that the parameters carry exactly the types the registry declares and none it does not:

```python
from pipelex.errors.registry.pipelex_codes import ConfigVariableMissingParams, PipelexErrorCode

params = ConfigVariableMissingParams(variable="OPENAI_API_KEY", source="env")
assert params.code == PipelexErrorCode.CONFIG_VARIABLE_MISSING
assert params.operator_only_params == frozenset({"variable", "source"})
```

An `identifier` or a `caller_text` is a `str`, an `integer` an `int`, a `seconds` a `float` and a `bytes` an `int`, neither ever negative, a `sha256` a lowercase hexadecimal `str`, an `enum` the `Literal` of its values, and a `list` a `list` of its items' type. An optional parameter is its type or `None`. `operator_only_params` names the parameters that only whoever runs the runtime may read, which an implementation leaves out of every problem it answers to a caller.

## The checks

`make check-error-registry` and the test suite check the source in three passes, each run only on a document the previous one accepts:

1. The format's JSON Schema, vendored from the standard, refuses a member missing, unknown or forbidden in its case, and a value outside its closed lists of domains, retry verdicts and step kinds.
2. The typed model Pipelex reads the registry with refuses the same documents, so that the model can never accept one the schema would not.
3. The rules a schema cannot state, which the standard applies to its own registry: a family or a code given twice, a code whose family is not declared, a family no code uses, a code or a family outside the `pipelex` prefix, a template naming a parameter its reader may not see, and a `see` reference to a documentation page this repository does not hold. A template may name only a declared parameter that is not optional, and an operator-only parameter only in the actor's step of an `operator` code.

To these, Pipelex adds the rules its own use of the registry needs:

- the core registry registers the `pipelex` prefix under the base URL the pages are published at, `https://docs.pipelex.com/errors`;
- every code a sentence names in backticks exists: a core code such as `provider.credential_refused` in the core registry, a `pipelex.` code in this one;
- every parameter name can be a field of the generated parameters model, so it is neither a Python keyword nor an attribute of a pydantic model.

## The standard's vendored files

The checks read two files of the standard, copied verbatim into `pipelex/cli/dev_cli/commands/error_registry/standard/`: the registry format's JSON Schema, `mthds-error-registry.schema.json`, and the core registry's snapshot, `mthds-error-registry.json`. `vendored.toml` beside them records the standard's repository, the commit and the version they were copied from, and the SHA-256 digest of each, which a test compares with the files. Nothing at run time reads these copies. To refresh them, copy both files from the standard's release, at the tag `v<version>` or from its release assets, and update the record.

The development CLI, where the checks and the generators live, is not shipped in the wheel, so neither are these files nor `jsonschema`, which only the checks use.

## The pages and the type URI

A code's type URI is the registry's base URL, a slash, then the whole code: `https://docs.pipelex.com/errors/pipelex.billing.credit_exhausted`. Its page is `docs/errors/pipelex/billing/credit_exhausted.md`, one directory per segment but the last, which the versioned site serves at `/latest/errors/pipelex/billing/credit_exhausted/`. A page is never named after the whole code, because the site's host answers a URL whose last segment holds a dot by redirecting it to the same URL without its trailing slash, where the page's relative links no longer resolve.

The site is static, with no server-side redirect, so the documentation's deployment closes the gap. `make docs-deploy-root`, which every documentation deploy runs, calls `pipelex-dev write-error-type-redirects` on its checkout of the `gh-pages` branch: for every code whose page the `latest` version holds, it writes `errors/<code>/index.html` at the site's root, a page that redirects to the code's `/latest/` page, and it removes the stub of a code `latest` no longer documents. The host answers the type URI, which has no trailing slash, by redirecting it to that directory. A code's type URI therefore resolves once a release that documents it is the latest version.

Before the error registry, every `PipelexError` class had a generated page at `errors/<kebab-class-name>/`, which its class-derived `type_uri` named. Those pages are retired, and the site's `404.html` sends such a URL to the [Error Codes](../errors/index.md) index.

## Adding or changing a code

1. Add or edit the entry in `pipelex/errors/registry/pipelex-error-registry.yaml`, declaring every member. A new family is declared under `families`, in the order the pages present them.
2. Run `make generate-error-registry`, then read the diff of the snapshot, the typed codes and the code's page.
3. Run `make check-error-registry`, or the tests under `tests/unit/pipelex/errors/registry/`.

A registered prefix's codes follow the standard's versioning: a new code or family is an addition, while a changed domain, retry verdict, step kind, status or parameter type changes what the runtime emits and is a breaking change for whoever branches on it, noted as such in the changelog. A reworded title or template is neither.

## Related

- [Error Model](../under-the-hood/error-model.md#error-codes-and-the-pipelex-error-registry): how errors are classified and reported.
- [Drift Contracts](drift-contracts.md): the derived checks, the registry's among them.
