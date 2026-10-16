---
title: "PipeFunc Requirements"
description: "How Pipelex checks a method's requirements.txt against the Python environment its PipeFunc steps run in, where the check runs on a sandbox-hosted deployment, and the plugin seam through which a deployment states its sandbox's packages."
---

# PipeFunc Requirements

A method declares the Python packages its own Python imports in a `requirements.txt` at the root of its method tree, under the rules of the MTHDS standard: each line is blank, a comment, or exactly one PEP 508 requirement. The author's view of the file is in [Method Trees](../building-methods/method-trees.md#python-packages-requirementstxt). This page is about where Pipelex checks it and how a deployment tells Pipelex what its PipeFunc sandbox holds.

## What is checked, and when

A method tree is checked when it holds a `requirements.txt` at its root and a `.py` file anywhere in it. Python is the proxy for "has code that could import a package" rather than "has a PipeFunc pipe", because a server receives a method's Python apart from its bundles: the runner loads a bundle's `.py` files from a directory it makes for the request, while the `.mthds` files arrive as content, so the directory holding the Python holds no pipe to judge it by.

The check runs in the library load, `LibraryManager.load_libraries` and `LibraryManager.load_from_blueprints` (for a bundle file named alone, whose tree is listed there), after every tree of the load is listed and before any of their Python is imported or captured, and before any pipe is built. It is `ensure_method_requirements_met` in `pipelex/libraries/method_requirements.py`. Each tree is judged once per load, and the environment is resolved only once a tree declares a requirement to judge, so a load declaring none never reads it.

A requirement whose marker is false in the environment is not needed there and is skipped. One is met when the environment holds a distribution of its name, compared normalized, at a version its specifier contains, pre-releases included, and when, for each extra it names, the requirements the distribution's metadata declares under that extra are met in turn.

## The environment the check reads

`resolve_pipe_func_package_environment` in `pipelex/libraries/package_environments.py` picks the environment from `interpreter.pipe_func.execution_mode`:

| Execution mode | Environment | What it reads |
| --- | --- | --- |
| `direct` | `InterpreterPackageEnvironment` | The distributions installed in the interpreter Pipelex runs in, through `importlib.metadata`, and this interpreter's own marker environment. Extras are followed through each distribution's `Requires-Dist`. |
| any other mode | `OfferedPackageEnvironment` | The package set the plugin providing the mode states for its sandbox, and nothing else. A marker variable the offer does not state cannot be judged, and a requirement with extras cannot be followed, so both are refused rather than judged against this process's own values. |

Locally the refusal names the method's folder, each requirement and why, and gives the `uv pip install --python <this interpreter>` command that installs them. On a sandbox-hosted deployment it names no path of the host, since the method's files lie in a directory the server made for the request.

## Where the check runs on a sandbox-hosted deployment

**On the runner, never on the worker or in the sandbox.** The runner is the process that holds the method's files and loads them, and the place a refusal reaches the caller before anything is dispatched:

- **A run** (`/execute`, `/start`) with a `files` or `bundle_b64` bundle, or by `method_ref`, loads the method's non-`.mthds` files as a library directory on the runner, through `acquire_library`, so the check refuses the method there, as a `422` naming each requirement, before any dispatch.
- **A validation by `method_ref`** (`/validate`) is dispatched whole to a validator that never reads the method's Python, a Temporal worker for instance, so `ApiRunner.validate_verdict` checks the fetched package's library directory first, through `ensure_library_dirs_requirements_met`, and returns a refusal as the invalid verdict, one item per line. Inline `mthds_contents` carry no Python and are not checked.
- **The worker** loads the library crate the runner built, which carries the method's Python sources but not its `requirements.txt`, so it never checks anything, and needs to know nothing of the sandbox's packages.

## The seam: stating the sandbox's packages

Pipelex cannot read a sandbox it never runs in, and it must not depend on the deployment that provides one, so the plugin providing an execution mode's executor states that mode's package set through its registrar, keyed by the same mode token:

```python
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig


def _sandbox_package_offer(pipe_func_config: PipeFuncConfig) -> PipeFuncPackageOffer | None:
    package_set = read_my_sandbox_package_set()  # the plugin's own reading of its image's lock, cached
    if package_set is None:
        return None
    return PipeFuncPackageOffer(
        environment=f"the Example sandbox image '{package_set.image}'",
        distributions={package.name: package.version for package in package_set.packages},
        marker_environment=package_set.marker_environment,
    )


class ExampleSandboxPlugin:
    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_pipe_func_executor(mode="example", factory=_make_executor)
        registrar.add_pipe_func_package_offer(mode="example", factory=_sandbox_package_offer)
```

- **`PipeFuncPackageOffer`** (`pipelex/plugins/pipe_func_package_offer_registry.py`) is closed, frozen plain data: `environment`, the place as a refusal names it to the method's author; `distributions`, each distribution's name with its exact installed version, the names compared normalized; and `marker_environment`, the PEP 508 marker values of the sandbox's interpreter. A variable left out of `marker_environment`, such as `python_full_version` when the image pins only its minor version, makes every requirement whose marker reads it refused.
- **The factory** receives the `PipeFuncConfig` and is called each time a method declaring requirements loads, never at registration, so it may read the plugin's own configuration and should cache what it computes. It answers `None` when it cannot state the offer.
- **It fails closed.** A mode with no registered offer, or whose factory answers `None`, meets no requirement: a method declaring one is refused with `PipeFuncPackageSetUnstatedError`, a `config`-domain fault of the deployment whose message is not caller-facing, rather than loading and failing inside the sandbox at its first import. A method declaring none still loads.
- **It is interpreter-layer**, like `add_pipe_func_executor`: a plugin published under `pipelex.plugins.kernel` that calls it is refused with `PluginLayerViolationError`. A second plugin stating the same mode is refused with `DuplicatePipeFuncPackageOfferError`, naming both.

`Pipelex.setup` builds the `PipeFuncPackageOfferRegistry` from the registrar beside the `PipeFuncExecutorRegistry` and puts it on the `InterpreterHub` (`get_pipe_func_package_offer_registry`).

### What our Daytona plugin supplies

For the hosted API, the Daytona sandbox plugin registers the offer for its `daytona` mode from the package set of the Daytona sandbox snapshot it boots, the lock its snapshot image is built from: the snapshot's distributions and versions, and the marker environment of its base image. The runner, where the check runs, must resolve the same snapshot name the worker's sandboxes boot from, since the worker is the process that creates them; a runner that cannot resolve it answers `None` and refuses every method declaring requirements.

## Errors

| Error | Domain | When |
| --- | --- | --- |
| [`MethodRequirementsFileError`](../errors/method-requirements-file-error.md) | `input` | The file holds a line the standard refuses, naming each, or is not UTF-8 text. |
| [`MethodRequirementsNotMetError`](../errors/method-requirements-not-met-error.md) | `input` | The environment does not meet a requirement, naming each and why. |
| [`PipeFuncPackageSetUnstatedError`](../errors/pipe-func-package-set-unstated-error.md) | `config` | A sandbox-hosted deployment states no package set for its execution mode. |

The first two are `LibraryLoadingError`s carrying one blueprint validation item per line, whose `source` is the file (its path locally, `requirements.txt` on a sandbox-hosted deployment) and whose `line` is the line's number, so a validation reports them as an invalid verdict located on the line. They are deliberately not `MethodTreeLoadError`s, which a server reports as its own fault around the library directories it loads, since the directory a server loads a caller's Python from is one of those.
