---
title: "The API Server"
description: "The Pipelex API server lives in this repository as the api/ workspace member: how it depends on the library, its environment, the gate and CI that cover it, its vendored inference tree, its image and how a release ships it."
---

# The API server

The Pipelex API server, the FastAPI runner published as the `pipelex/pipelex-api` image and the `pipelex-api` package, lives in this repository as the `api/` directory. It is the reference implementation of the MTHDS Protocol, and the base the hosted runner composes. Its own guide is `api/CLAUDE.md`, and its reference documentation is the [API Server](../api-server/index.md) section of this site, whose pages live in `docs/api-server/`.

## A workspace member

The repository is a uv workspace. The root project is the `pipelex` library, untouched, and `api/` is a second member, the `pipelex-api` distribution, whose import package is `pipelex_api`. The root `pyproject.toml` declares it:

```toml
[tool.uv.workspace]
members = ["api"]
```

The member depends on the library through the workspace (`pipelex = { workspace = true }` in its `[tool.uv.sources]`), so the server always runs the library of the same commit, and the repository keeps a single `uv.lock` at its root. The `pipelex` wheel and sdist are unaffected: both restrict themselves to `packages = ["pipelex"]`.

The two are released together, under one version number. The member declares its version dynamic and hatch reads it from the root `pyproject.toml` (`[tool.hatch.version]` in `api/pyproject.toml`), so a release bumps one file, and the member's `[tool.uv] cache-keys` name the root file so that uv notices the bump.

Its dependencies are dynamic too. They are written in `[tool.hatch.metadata.hooks.custom]` of `api/pyproject.toml` rather than in `[project]`, and `api/hatch_build.py` writes them into the distribution's metadata: each requirement of `lockstep-dependencies`, which is `pipelex` with the server's extras, pinned to `==` the release's own version, then the other `dependencies` as written. In the workspace uv ignores a version specifier on a workspace source, so the pin changes nothing locally and never goes stale; in a published `pipelex-api` it is what makes an install take exactly the pipelex the server was released with. A server dependency is therefore added or changed in that table by hand, and the root's `uv lock` picks it up: `uv add` would write a static `[project] dependencies` list, which hatch refuses beside the dynamic one.

## Its own environment

The server is tested with exactly the dependencies it declares, which are not the library's development set: pipelex with the server's extras and without `cli`, plus FastAPI, uvicorn and the server's own tools. Its Makefile therefore points every uv command at `api/.venv` (`UV_PROJECT_ENVIRONMENT`), where pipelex is an editable install of this repository's source, so a library edit reaches the server without a reinstall. The targets that need that environment provision it themselves.

## The gate covers it

The root `make agent-check` ends with `make api-agent-check`, which runs `make -C api agent-check`: the member's install, ruff, pyright and mypy under its own configuration, then two drift checks. The root `make agent-test` ends with `make api-agent-test`, the server's unit tests. A library change that breaks the server therefore fails the gate in the change that makes it, and so does one that moves the server's wire or its inference tree:

- **`make -C api openapi-check`** compares the committed OpenAPI artifact, `docs/api-server/openapi/pipelex-api.openapi.yaml`, with what the app generates. It sits among the server's pages, so the docs site publishes it beside the pages that link to it. pipelex's own models ride the server's wire (the run result, the bundle blueprint, the validation error vocabulary), so a library change can move the artifact with no change to the server's code. Regenerate it with `make -C api openapi-export` and read the diff: it is what the change did to the server's callers.
- **`make -C api kit-check`** compares the server's vendored inference tree with the kit.

## Pull-request CI covers it

Every pull request runs the server's checks, with no path filter, because a change to the library alone can break the server:

- **`Lint (api)`**, in `lint-check.yml`, runs the member's ruff, pyright and mypy, `openapi-check` and `kit-check` in its own environment.
- **`Tests (api)`**, in `tests-check.yml`, runs its unit tests.
- **`Tests (packages)`** builds the `pipelex` and `pipelex-api` wheels and sdists as a release would, checks the exact pin on `pipelex` in the `pipelex-api` metadata with `api/scripts/check_lockstep_pin.py`, installs the two wheels together under the lock's versions and imports the server from them.
- **`Tests (api image)`** builds the image from the repository root and smoke-tests it with `make -C api docker-smoke`, which boots it, waits for `/health` and checks that `/v1/version` reports this version for both the server and the pipelex it runs.

They block through the `Lint (all)` and `Tests (all)` aggregates. Those run the floor Python version only, as they do for the library; on a pull request into `main`, the pre-main gates add the server to every supported version, in each `Lint fresh (pyX)` leg and in the `Tests full (api, pyX)` jobs.

The root ruff configuration excludes `api/`, which the member's gate lints under its own. The root plxt configuration formats and lints the member's TOML and MTHDS files like any other, except its vendored inference tree, which the sync keeps byte-identical to the kit, and its deliberately invalid sample bundles.

## The vendored inference tree

The image serves the models its `/root/.pipelex/inference/` tree declares, which is `api/.pipelex/inference/`, and pipelex never falls back to the kit in its own package once a config directory exists. `api/scripts/sync_vendored_kit.py` keeps that tree in step with `pipelex/kit/configs/inference/`: the backend files, the routing profiles, the numbered deck files and the manifests are mirrored byte for byte, and only the `enabled` switches in `backends.toml` and the `x_custom_*` deck overrides are the server's own choice.

`make up-kit-configs` (`ukc`), the step a kit change already takes, runs that sync after mirroring `.pipelex/` into the kit, so the server's tree moves in the same change. The tree stays committed rather than generated when the image is built, because `make run` and the server's tests read it, and because the sync can refuse a kit entry it has no rule for, which a person has to resolve before a release rather than during one.

## The image

The image is built with the repository root as its context, so it installs the pipelex of the same commit:

```bash
docker build -f api/Dockerfile .
```

`make -C api docker-build` runs exactly that, and `make -C api docker-smoke` boots what it built and checks the versions it reports. The root `.dockerignore` keeps the context down to the files the build reads. It is an allowlist, and it sits at the root rather than beside the Dockerfile because the legacy builder reads no other ignore file, and without one it would copy local override files, which can hold credentials, into the image.

## How a release ships it

A pipelex release publishes three artifacts under its one version, all from `.github/workflows/publish-pypi.yml`, which fires when the release pull request merges into `main`:

1. **`pipelex` on PyPI**, as before: `build`, then `publish-to-pypi`, then `github-release`, which tags the release commit and refuses a commit an existing tag does not name.
2. **`pipelex-api` on PyPI**: `build-api` builds the server's wheel and sdist and refuses them unless `check_lockstep_pin.py` finds `pipelex[...]==X.Y.Z` in both. `publish-to-pypi` waits for it, so a server that does not build stops the release before `pipelex` is uploaded, while the version can still ship from a fixed commit. Then `publish-api-to-pypi` uploads them through trusted publishing in the same `pypi` environment. It waits for `github-release`, so the `pipelex` wheel they pin is on PyPI and the tag guard has accepted the commit they were built from before a file reaches PyPI, where it can never be replaced.
3. **`pipelex/pipelex-api:X.Y.Z` on Docker Hub**: once both distributions are on PyPI, `publish-docker-hub` calls `.github/workflows/publish-docker-hub.yml` with the version. It checks out the commit the `vX.Y.Z` tag names, runs `make -C api deploy-docker-hub`, which builds the image, smoke-tests it and pushes it, and confirms the tags through Docker Hub's API. `latest` moves only when the version is the newest stable release, so a pre-release, or a retry of an older release, leaves it where it is. The Docker Hub overview is not part of the release: it is still updated by hand, by pasting `api/README.md` into the repository's overview on Docker Hub when it has changed.

A failed publish is retried with "Re-run failed jobs" on the release run, which re-runs only what failed. A version Docker Hub already serves is never built again, because a rebuild would be a different image under the same tag: a retry that finds it there only moves `latest`, when the version is the newest stable release, and confirms the tags. The image can also be published on its own with `gh workflow run publish-docker-hub.yml --ref <branch> -f version=X.Y.Z`, which helps when the fix is a change to that workflow file, which a re-run would not pick up: dispatched from the branch carrying the fix, it still builds the commit the tag names. Such a fix must use only actions the organization's Actions policy allows, or GitHub rejects the whole workflow at startup and nothing publishes; pull-request CI never loads these workflows, so [`make check-actions-allowlist`](actions-allowlist.md) checks every workflow against the policy's mirror on each pull request.

What the release needs configured on GitHub and PyPI: the `DOCKER_HUB_TOKEN` secret on the repository, a token for the `pipelex` Docker Hub account that can push the image; and a PyPI trusted publisher for the `pipelex-api` project with owner `Pipelex`, repository `pipelex`, workflow `publish-pypi.yml` and environment `pypi`, the same as `pipelex`'s.
