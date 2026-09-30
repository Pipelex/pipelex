---
title: "The API Server"
description: "The Pipelex API server lives in this repository as the api/ workspace member: how it depends on the library, its environment, the gate that covers it, its vendored inference tree and its image."
---

# The API server

The Pipelex API server, the FastAPI runner published as the `pipelex/pipelex-api` image, lives in this repository as the `api/` directory. It is the reference implementation of the MTHDS Protocol, and the base the hosted runner composes. Its own guide is `api/CLAUDE.md`, and its reference documentation is under `api/docs/`.

## A workspace member

The repository is a uv workspace. The root project is the `pipelex` library, untouched, and `api/` is a second member, the `pipelex-api` distribution, whose import package is `pipelex_api`. The root `pyproject.toml` declares it:

```toml
[tool.uv.workspace]
members = ["api"]
```

The member depends on the library through the workspace (`pipelex = { workspace = true }` in its `[tool.uv.sources]`), so the server always runs the library of the same commit, and the repository keeps a single `uv.lock` at its root. The `pipelex` wheel and sdist are unaffected: both restrict themselves to `packages = ["pipelex"]`.

The two are released together, under one version number. The member's dependency names that version exactly, `pipelex[...]==X.Y.Z`, which is what the published `pipelex-api` wheel declares, and `uv lock` refuses a root version the pin no longer names, so a release moves both.

## Its own environment

The server is tested with exactly the dependencies it declares, which are not the library's development set: pipelex with the server's extras and without `cli`, plus FastAPI, uvicorn and the server's own tools. Its Makefile therefore points every uv command at `api/.venv` (`UV_PROJECT_ENVIRONMENT`), where pipelex is an editable install of this repository's source, so a library edit reaches the server without a reinstall. The targets that need that environment provision it themselves.

## The gate covers it

The root `make agent-check` ends with `make api-agent-check`, which runs `make -C api agent-check`: the member's install, ruff, pyright and mypy under its own configuration, then two drift checks. The root `make agent-test` ends with `make api-agent-test`, the server's unit tests. A library change that breaks the server therefore fails in the change that makes it, and so does one that moves the server's wire or its inference tree:

- **`make -C api openapi-check`** compares the committed OpenAPI artifact, `api/docs/openapi/pipelex-api.openapi.yaml`, with what the app generates. pipelex's own models ride the server's wire (the run result, the bundle blueprint, the validation error vocabulary), so a library change can move the artifact with no change to the server's code. Regenerate it with `make -C api openapi-export` and read the diff: it is what the change did to the server's callers.
- **`make -C api kit-check`** compares the server's vendored inference tree with the kit.

The root configurations of ruff and plxt exclude `api/`, which the member's gate covers under its own.

## The vendored inference tree

The image serves the models its `/root/.pipelex/inference/` tree declares, which is `api/.pipelex/inference/`, and pipelex never falls back to the kit in its own package once a config directory exists. `api/scripts/sync_vendored_kit.py` keeps that tree in step with `pipelex/kit/configs/inference/`: the backend files, the routing profiles, the numbered deck files and the manifests are mirrored byte for byte, and only the `enabled` switches in `backends.toml` and the `x_custom_*` deck overrides are the server's own choice.

`make up-kit-configs` (`ukc`), the step a kit change already takes, runs that sync after mirroring `.pipelex/` into the kit, so the server's tree moves in the same change. The tree stays committed rather than generated when the image is built, because `make run` and the server's tests read it, and because the sync can refuse a kit entry it has no rule for, which a person has to resolve before a release rather than during one.

## The image

The image is built with the repository root as its context, so it installs the pipelex of the same commit:

```bash
docker build -f api/Dockerfile .
```

`make -C api docker-build` runs exactly that. `api/Dockerfile.dockerignore`, the ignore file BuildKit reads for that Dockerfile, keeps the context down to the files the build reads.
