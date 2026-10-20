---
title: "PipeFunc Requirements"
description: "How Pipelex checks a method's requirements.txt against the Python environment its PipeFunc steps run in, where the check runs on a sandbox-hosted deployment, and the plugin seam through which a deployment states the packages its sandbox offers for a method's requirements."
---

# PipeFunc Requirements

A method declares the Python packages its own Python imports in a `requirements.txt` at the root of its method tree, under the rules of the MTHDS standard: each line is blank, a comment, or exactly one PEP 508 requirement. The author's view of the file is in [Method Trees](../building-methods/method-trees.md#python-packages-requirementstxt). This page is about where Pipelex checks it and how a deployment tells Pipelex what its PipeFunc sandbox holds.

## What is checked, and when

A method tree is checked when it lies on this host's disk, holds a `requirements.txt` at its root, and holds a `.py` file anywhere in it. Python is the proxy for "has code that could import a package" rather than "has a PipeFunc pipe", because the check reads the tree's listing and never its bundles: a load runs it before it parses any of them, and the API server, which receives a method as a tree holding its bundles and its Python together, sent in `files` or `bundle_b64` or fetched by `method_ref`, writes the tree out and judges it before loading anything (see [below](#where-the-check-runs-on-a-sandbox-hosted-deployment)). Python that no step names can import a package too, such as a module a step's function imports, or, in the `direct` mode, a module defining a concept's structure class.

The check is `pipelex/libraries/method_requirements.py`, and a load runs it at three places, each before any Python of the tree is imported, or scanned for structure classes on a sandbox-hosted deployment, and before any of its pipes is built. A load never imports a `PipeFunc`'s module anyway: the step imports its function's module by its import path when it first binds it, in a validation's dry run or its first run, which comes after the load and its check, and the only Python a direct-mode load imports, the modules defining a concept's structure class, is imported after the check too.

- `LibraryManager.load_libraries` checks every tree of its library directories, and the tree of each bundle file it is handed, once all of them are listed.
- `LibraryManager.load_from_blueprints` checks the tree of every bundle read from this host's disk, on every load, taking as judged only a tree the run's listing holds as met (below): a blueprint an earlier load placed in its tree is judged again when that load's listing was another, and a refused one always is.
- A dependency package, one a bundle calls by its address, is checked as soon as its tree is listed, before any of its bundles loads.

**Each tree is judged once per run.** The listing a run reads its method trees through, a `MethodTreeListing` (`pipelex/libraries/method_tree_listing.py`), keeps each tree a check of the run found met, by its directory and its digest, so a later check of the same run takes the verdict as given: `load_from_blueprints` does not judge again a tree `load_libraries` just judged, and a load does not judge again a tree the API server's check of the request found met. A refused tree is never kept, so a check that comes after a refusal judges it again, and a load handed no listing makes one of its own, shared by its steps. The verdict does not depend on whether a refusal may name host paths, which changes only its wording, so a server's check and the load after it share it.

**A load never runs on the event loop.** It is blocking work: it lists and hashes the method's files, asks the package-offer factory to judge its requirements, reads the methods installed on this host and may fetch a package a bundle calls by its address. So every load Pipelex reaches from asynchronous code, a run's (`acquire_library_async` in `pipelex/pipeline/execution_seams.py`), a validation's (`validate_bundle`) and those of the commands that run a loop, runs in a worker thread of the method-load pool through `run_method_load` (`pipelex/libraries/method_load_threads.py`), the reading and parsing of the bundles it loads included. The thread runs in a copy of its caller's context, so it reads the current library and every other context variable its caller set, and what it sets stays in its copy. When its caller is cancelled, the shutdown of `asyncio.run` included, a load no thread has taken yet is withdrawn and never runs, and a running one is waited for until it ends before the cancellation goes through, since a thread cannot be interrupted, so a library is torn down only when nothing still loads into it.

**The method-load pool is bounded.** At most `METHOD_LOAD_MAX_THREADS` loads, four, run at once in a process, together with the blocking work around them, such as the API server writing a request's tree to disk and judging its requirements. A load asked for while every thread is busy waits for one, its caller awaiting on the event loop without blocking it. The pool is its own rather than asyncio's default executor, so slow loads, each of which can hold its thread for seconds while a package is fetched or a sandbox resolves requirements, never take the threads every other blocking call of the process borrows, such as a DNS lookup. Loads running in parallel import the modules defining their structure classes under one lock, which their class discovery also holds, so no load takes another's module half executed.

A requirement whose marker is false in the environment is not needed there and is skipped. One is met when the environment holds a distribution of its name, compared normalized, at a version its specifier contains, pre-releases included, and when, for each extra it names, the requirements the distribution's metadata declares under that extra are met in turn. A marker that cannot be evaluated, such as one comparing as versions a value that is not one (which releases of `packaging` before 22 refuse), refuses its requirement rather than the load.

## The environment the check reads

`resolve_pipe_func_package_environment` in `pipelex/libraries/package_environments.py` picks the environment from `interpreter.pipe_func.execution_mode`, for one tree's requirements at a time:

| Execution mode | Environment | What it reads |
| --- | --- | --- |
| `direct` | `InterpreterPackageEnvironment` | The distributions installed in the interpreter Pipelex runs in, through `importlib.metadata`, and this interpreter's own marker environment, whatever the requirements. Extras are followed through each distribution's `Requires-Dist`. |
| any other mode | `OfferedPackageEnvironment` | The package set the plugin providing the mode states its sandbox offers for the tree's requirements, and nothing else: a fixed package set, or an environment the plugin builds for those requirements. A marker variable the offer does not state cannot be judged, and a requirement with extras cannot be followed, so both are refused rather than judged against this process's own values. The plugin may instead refuse the requirements with its own reason, when no environment it can build holds them, and the method is then refused with that reason. |

Each tree declaring requirements is judged against the environment resolved for its own requirements, so when one check judges several trees, such as the library directories of one load, each gets the offer stated for it and never another tree's.

In the `direct` mode, a method's Python is imported into the process that loads it, when its steps first bind their functions, and that is the process the check judges. A distributed orchestrator, such as our Temporal plugin, never carries a method's Python to its worker: the library crate names the step's method tree by its digest, and in a sandbox mode the call's files are read through the method file store by whoever runs it, for the sandbox to import them, never this process. A worker in the `direct` mode therefore runs only the functions its own deployment installed, whose packages are that deployment's to install, and the API server refuses a caller's Python outright unless it is sandbox-hosted (a `501` `pipelex.deployment.custom_code_requires_sandbox`). So no worker needs to repeat the check.

## How a refusal names the method

The file is always named by its path in the method's tree, `requirements.txt`, on every item of a refusal. Paths on the host, the method's root and this interpreter's executable, are named only where the refusal may name them:

- **A check inside a load names them**, since its refusal belongs either to the caller's own disk, as on a local run, or to the host, around a server's own library directories, where `reporting_host_library_tree_faults` turns it into the host's fault and withholds it from the caller. Locally, the refusal therefore names the method's folder, each requirement and why, and the `uv pip install --python <this interpreter>` command that installs them.
- **A dependency package is named by its address**, as its bundles are, and its file by `<address>/requirements.txt`, never by the directory it was installed or fetched into.
- **A server checking a caller's method it holds in a directory of its own names no path on the host at all** (`ensure_served_method_requirements_met`): the method is "the method", the interpreter is "the Python interpreter Pipelex runs in", and the install command names no interpreter path.

## A host's own library directories

A server loads its own library directories (`PIPELEXPATH`, the instance defaults, installed libraries) beside a caller's bundles. A method of those directories whose requirements are not met is the deployment's fault, not the caller's: around such a load, `reporting_host_library_tree_faults` turns the refusal into a `HostLibraryRequirementsError`, carrying `pipelex.config.invalid` and answered with a `500` whose message, naming paths on the host, rides only the operator view's diagnostics, as it turns a tree it cannot list into a `HostLibraryTreeError`. Any other refusal of such a method while it loads becomes a `HostLibraryLoadRefusalError`, carrying `pipelex.config.invalid` too (see [Library Configuration](../configuration/config-technical/library-config.md)).

## Where the check runs on a sandbox-hosted deployment

**On the runner first, and never in the sandbox.** The runner is the process that holds the method's files, and the place a refusal reaches the caller before anything is dispatched. The runner loads the directory it makes for a request's files as one of its own library directories, where a refusal is the host's fault, so it judges the caller's method first, through `ensure_served_method_requirements_met`, run off the event loop since it lists and hashes the method's files. It lists them through a `MethodTreeListing` (`pipelex/libraries/method_tree_listing.py`) it hands to the run or the validation serving the request, which loads the trees from it, so a request lists and hashes the method's files once:

- **A run** (`/execute`, `/start`) with a `files` or `bundle_b64` bundle, or by `method_ref`, is refused there as a `422` naming each requirement, before the method's files load and before any dispatch.
- **A validation of a method tree** (`/validate`), sent in `files` or fetched by `method_ref`, is judged there too, whether its validator runs in the runner's process or on a worker it is dispatched to, a Temporal worker for instance: `ApiRunner.validate_verdict` returns a refusal as the invalid verdict, one item per line, before the validator is reached. Inline `mthds_contents` carry no Python and are not checked.
- **A directory of the request that cannot be listed** stays the host's fault, a `500` `HostLibraryTreeError` carrying `pipelex.config.invalid`, as the load reports it.
- **The worker running a run** loads the library crate the runner built, which names each step's method tree by its digest and carries none of the tree's files, its Python and its `requirements.txt` included, so loading it checks nothing. A `PipeFunc` call's files are read on the worker, through the method file store its host installs (`HubSlot.METHOD_FILE_STORE`), and handed to the sandbox, which loads the same crate and checks nothing either.
- **A worker a method tree's validation is dispatched to** receives the method's trees rather than a crate (`BundleValidatorProtocol`) and loads them, so it judges the requirements again, in its own process and through its own listing, against the package set the plugins of its own process state for the mode. Its deployment therefore registers the same offer as the runner's: a worker stating none refuses every method declaring requirements with `PipeFuncPackageSetUnstatedError`.

## The seam: stating the sandbox's packages

Pipelex cannot read a sandbox it never runs in, and it must not depend on the deployment that provides one, so the plugin providing an execution mode's executor states that mode's packages through its registrar, keyed by the same mode token. The plugin is asked for one method's requirements at a time, so a mode whose sandbox is not one fixed package set, such as one building an environment for each method, states the environment it would run that method in:

```python
from pipelex.libraries.method_requirements import requirements_needed_in
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer, PipeFuncPackageOfferRequest, PipeFuncPackageRefusal


def _sandbox_package_offer(request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
    base = read_my_sandbox_package_set()  # the plugin's own reading of its image's lock, cached
    if base is None:
        return None
    # Only what the sandbox needs: a requirement whose marker is false in its interpreter is neither built nor refused.
    needed = requirements_needed_in(requirements=request.requirements, marker_environment=base.marker_environment)
    environment = environment_for(needed)  # resolved over the base, cached by the requirements' texts
    if environment.unresolvable:
        return PipeFuncPackageRefusal(environment="the Example sandbox", reason=environment.explanation)
    return PipeFuncPackageOffer(
        environment=f"the Example sandbox image '{environment.image}'",
        distributions={package.name: package.version for package in environment.packages},
        marker_environment=base.marker_environment,
    )


class ExampleSandboxPlugin:
    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_pipe_func_executor(mode="example", factory=_make_executor)
        registrar.add_pipe_func_package_offer(mode="example", factory=_sandbox_package_offer)
```

A mode with one fixed package set ignores the requirements and answers its package set whatever they are.

- **The request**, `PipeFuncPackageOfferRequest` (`pipelex/plugins/pipe_func_package_offer_registry.py`), carries the `PipeFuncConfig` and `requirements`, every requirement the method's `requirements.txt` declares, in the file's order, each a `RequirementLine` (`pipelex/core/method_trees/requirements_file.py`: its line number, its text as written and the parsed PEP 508 requirement). A plugin judging them against a package set of its own uses Pipelex's judgment, `unmet_requirements` with an `OfferedPackageEnvironment`, so it sets aside exactly what the check would find met.
- **The markers are the factory's to evaluate.** The requirements arrive with their markers unevaluated, since Pipelex cannot evaluate a marker before it knows the environment the mode would run the method in. A requirement whose marker is false in that environment is not needed there, and the check skips it, so the factory evaluates the markers against the marker environment of the place it would offer, builds nothing for a requirement the place does not need, and never refuses for one: a refusal rests only on requirements whose markers hold there. `requirements_needed_in` (`pipelex/libraries/method_requirements.py`) picks them out as the check would, keeping a requirement whose marker reads a variable the marker environment does not state, or cannot be evaluated, which the check refuses rather than skips.
- **`PipeFuncPackageOffer`** is closed, frozen plain data: `environment`, the place as a refusal names it to the method's author; `distributions`, each distribution's name with its exact installed version, the names compared normalized; and `marker_environment`, the PEP 508 marker values of the sandbox's interpreter. A variable left out of `marker_environment`, such as `python_full_version` when the image pins only its minor version, makes every requirement whose marker reads it refused. Pipelex judges every requirement against the offer, one built for them included, so an offer that does not meet them refuses the method as a fixed package set would, naming each requirement.
- **`PipeFuncPackageRefusal`** is the answer when no environment of the mode can hold the requirements the place needs, such as a version conflicting with a package the sandbox's base pins, or a package with no wheel for the sandbox: `environment`, the place as the refusal names it, and `reason`, the plugin's own words, such as its resolver's explanation. The method is refused with `MethodRequirementsNotMetError`, a fault of the method's carrying `method.dependency_missing`, whose message, "The method needs Python packages that the Example sandbox cannot offer, as its requirements.txt declares: …", carries the reason, with one item on the file and no line, since the reason is about the requirements together. The reason reaches the method's author, a server's caller included, so it names no path on the host.
- **The factory is synchronous and never called on a thread running an event loop, and caching by the requirements is the plugin's job.** The check runs inside the library load, which is synchronous, and [every load Pipelex reaches from asynchronous code runs in a worker thread of the method-load pool](#what-is-checked-and-when), as the API server's check of a served method does, while a synchronous caller, such as a command loading a method before it starts a loop, calls it on its own thread, which runs none. So a factory may block for as long as its work takes, and it must not use an event loop of its caller's, since none runs on its thread and the one its caller's code runs on, if any, belongs to another thread. Pipelex enforces the rule: a factory about to be called on a thread running an event loop is not called, and the load fails with `PipelexUnexpectedError`, so a host that calls a load itself from asynchronous code, such as a worker's activity loading a library directly, moves it off the loop the same way, with `run_method_load`. An asynchronous factory would buy nothing short of making every load asynchronous, so the seam stays synchronous. Pipelex calls the factory for each tree declaring requirements the first time a check of a run judges it, never at registration, and keeps the tree's verdict for the rest of the run only when the tree meets its requirements: a load asks once per tree, however many of its steps judge the tree, and on the API server the check of a served method asks for the request, the load after it asking nothing. Pipelex keeps no answer across runs, so the next run, or the next request, asks again for the same requirements. A factory whose answer takes time, such as one resolving the requirements with `uv`, which takes seconds the first time, bounds the work with a timeout of its own and caches its answers by the requirements' texts, so only a process's first check of a requirement set pays for it.
- **A fault of the plugin's own is not a refusal.** A resolver the plugin cannot reach, or one outlasting its timeout, says nothing about the method: the factory raises it as an error of the plugin's, which Pipelex lets through, rather than answering a `PipeFuncPackageRefusal`, which would blame the method's author.
- **It fails closed.** A mode with no registered offer, or whose factory answers `None`, meets no requirement: a method declaring one is refused with `PipeFuncPackageSetUnstatedError`, a fault of the deployment carrying `runtime.misconfigured`, whose message only the operator view carries, rather than loading and failing inside the sandbox at its first import. Its message says which of the two happened: no plugin registers an offer for the mode, or the registered one could not state the packages, whose remedy is in the plugin's configuration. A method declaring none still loads.
- **It is interpreter-layer**, like `add_pipe_func_executor`: a plugin published under `pipelex.plugins.kernel` that calls it is refused with `PluginLayerViolationError`. A second plugin stating the same mode is refused with `DuplicatePipeFuncPackageOfferError`, naming both.

`Pipelex.setup` builds the `PipeFuncPackageOfferRegistry` from the registrar beside the `PipeFuncExecutorRegistry` and puts it on the `InterpreterHub` (`get_pipe_func_package_offer_registry`).

### What our Daytona plugin supplies

For the hosted API, the Daytona sandbox plugin states the package set of the Daytona sandbox snapshot it boots, the lock its snapshot image is built from: the snapshot's distributions and versions, and the marker environment of its base image. The runner, which checks a method before dispatching anything, must resolve the same snapshot name the worker's sandboxes boot from, since the worker is the process that creates them; a runner that cannot resolve it answers `None` and refuses every method declaring requirements. A method needing packages the base snapshot lacks runs in an environment the plugin builds for its requirements when a PipeFunc call provisions its box, and since the factory receives the requirements, the plugin can state that environment when the method loads, or refuse the requirements with its resolver's explanation.

## Errors

| Error | Code | When |
| --- | --- | --- |
| `MethodRequirementsFileError` | `method.package_invalid` | The file holds a line the standard refuses, naming each, or is not UTF-8 text. |
| `MethodRequirementsNotMetError` | `method.dependency_missing` | The environment does not meet a requirement, naming each and why, or the deployment refuses the requirements with its own reason, no environment it can build holding them. For a requirement not met, its `name` is the distribution that fails the requirement: the one required, or one an extra of it needs, with the `reason` `not_found` when it is missing and `no_matching_version` when the version held is one the requirement refuses. |
| `HostLibraryRequirementsError` | `pipelex.config.invalid` | A method of a host's own library directories, loaded beside a caller's bundles, is refused for its requirements. |
| `PipeFuncPackageSetUnstatedError` | `runtime.misconfigured` | A sandbox-hosted deployment states no package set for its execution mode. |

The first two are `LibraryLoadingError`s carrying one blueprint validation item per line, whose `source` is the file's path in the tree and whose `line` is the line's number, so a validation reports them as an invalid verdict located on the line. They are deliberately not `MethodTreeLoadError`s, which a server reports as its own fault around the library directories it loads.
