# ruff: file-ignore[implicit-namespace-package] - a standalone probe script, deliberately not a package
"""OQ1: which library does a dependency pipe's bare sub-pipe ref resolve against?

A dependency package is loaded into an isolated *child* library, and its pipes are ALSO registered
in the host library under aliased keys (`alias->domain.code`). Two readers then look up the same
authored bare sub-pipe ref, and the question this probe answers is whether they agree:

- **validation** (`Library.validate_pipe_library_with_libraries`) special-cases a dependency pipe:
  for an aliased key, a bare sub-pipe code is looked up in the CHILD library;
- **execution** (`SubPipe.run_pipe` -> `interpreter_hub.get_required_pipe`) has no such
  special-case: it asks the ambient current library — the HOST — with a strict key lookup and no
  fallback, so a bare code matches nothing there. (When this probe was first run, the host lookup
  instead ended in a crate-wide bare-code fall-through that explicitly SKIPPED `alias->` entries —
  same outcome for a dependency's bare ref, different mechanism.)

The probe builds a dependency whose exported entry is a `PipeSequence` calling a bare same-domain
helper, loads it through the real dependency loader, and asks both readers. It runs three shapes:

1. no manifest exports (every dependency pipe public), host declares nothing;
2. no manifest exports, host declares its OWN pipe under the same bare code — the case that decides
   between "fails loudly" and "silently runs the wrong pipe";
3. manifest `[exports]` naming only the entry pipe — what a published package actually ships. The
   export filter drops the authored helper from the dependency's OWN child library, so this shape
   fails differently, and earlier, than shape 1.

It also asks the host for the ref the build-time qualification pass WOULD produce
(`dep_domain.helper`), which is the OQ1 go/no-go question.

    .venv/bin/python wip/pipe-refs/probes/dep-subpipe-scope.py  # needs the venv: this probe imports pipelex

No credentials and no inference backend are needed; nothing is executed, only resolved.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest

from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries.library import Library
from pipelex.libraries.library_manager import LibraryManager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipelex import Pipelex

ALIAS = "helper_dep"
DEP_DOMAIN = "probe_dep_domain"
HOST_DOMAIN = "probe_host_domain"
BARE_HELPER_CODE = "probe_helper"

# The dependency: an exported entry sequence whose only step is a BARE same-domain helper ref.
DEP_MTHDS = f"""\
domain      = "{DEP_DOMAIN}"
description = "Dependency whose entry pipe calls a bare same-domain helper"

[pipe.probe_entry]
type        = "PipeSequence"
description = "Entry point, calling a bare same-domain helper"
inputs      = {{ doc = "Text" }}
output      = "Text"
steps       = [{{ pipe = "{BARE_HELPER_CODE}", result = "helped" }}]

[pipe.{BARE_HELPER_CODE}]
type        = "PipeLLM"
description = "the DEPENDENCY's own helper"
inputs      = {{ doc = "Text" }}
output      = "Text"
prompt      = "Help with $doc, the dependency way"
"""

# A host that declares its own pipe under the SAME bare code as the dependency's helper.
HOST_COLLIDING_MTHDS = f"""\
domain      = "{HOST_DOMAIN}"
description = "Host declaring its own pipe under the dependency helper's bare code"

[pipe.{BARE_HELPER_CODE}]
type        = "PipeLLM"
description = "the HOST's unrelated pipe, which happens to share the bare code"
inputs      = {{ doc = "Text" }}
output      = "Text"
prompt      = "Help with $doc, the host way"
"""


def describe(pipe: PipeAbstract | None) -> str:
    if pipe is None:
        return "None"
    return f"{pipe.pipe_ref}  <- {pipe.description}"


def build_resolved_dep(dep_dir: Path, *, exported_pipe_codes: set[str] | None) -> ResolvedDependency:
    """`exported_pipe_codes=None` means no manifest exports — every pipe public."""
    dep_file = dep_dir / "dep.mthds"
    dep_file.write_text(DEP_MTHDS, encoding="utf-8")
    manifest = MethodsManifest(
        address="github.com/org/probe-helper-dep",
        version="1.0.0",
        description="Probe dependency package",
    )
    return ResolvedDependency(
        alias=ALIAS,
        address="github.com/org/probe-helper-dep",
        manifest=manifest,
        package_root=dep_dir,
        mthds_files=[dep_file],
        exported_pipe_codes=exported_pipe_codes,
    )


def ask(*, label: str, library: Library, pipe_code: str) -> None:
    try:
        found = library.pipe_library.get_optional_pipe(pipe_code=pipe_code)
    except BaseException as exc:  # ruff: ignore[blind-except] - naming *which* error escapes IS the measurement here
        print(f"   {label:<58} -> {type(exc).__name__}: {exc}")
    else:
        print(f"   {label:<58} -> {describe(found)}")


def report(*, title: str, library: Library, library_id: str) -> None:
    print(f"\n===== {title} =====")
    print("   host pipe_library keys :", sorted(library.pipe_library.root))
    child_library = library.dependency_libraries[ALIAS]
    print("   child pipe_library keys:", sorted(child_library.pipe_library.root))
    print()
    print("   LOAD-TIME VERDICT — library.validate_library()")
    try:
        with scoped_current_library(library_id=library_id):
            library.validate_library()
    except BaseException as exc:  # ruff: ignore[blind-except] - naming *which* error escapes IS the measurement here
        print(f"   {'':<58} -> {type(exc).__name__}: {exc}")
    else:
        print(f"   {'':<58} -> valid")
    print()
    print(f"   VALIDATION reader — child library ({BARE_HELPER_CODE!r}: authored spelling; qualified: what validation asks post-pass)")
    ask(label="child.get_optional_pipe(bare)   [pre-qualification spelling]", library=child_library, pipe_code=BARE_HELPER_CODE)
    ask(
        label=f"child.get_optional_pipe('{DEP_DOMAIN}.{BARE_HELPER_CODE}')   [after the pass]",
        library=child_library,
        pipe_code=f"{DEP_DOMAIN}.{BARE_HELPER_CODE}",
    )
    print()
    print("   EXECUTION reader — host library (what SubPipe.run_pipe asks)")
    ask(label=f"host.get_optional_pipe({BARE_HELPER_CODE!r})   [pre-qualification spelling]", library=library, pipe_code=BARE_HELPER_CODE)
    ask(
        label=f"host.get_optional_pipe('{DEP_DOMAIN}.{BARE_HELPER_CODE}')   [after the pass]",
        library=library,
        pipe_code=f"{DEP_DOMAIN}.{BARE_HELPER_CODE}",
    )


def main() -> None:
    Pipelex.make(needs_inference=False)
    manager = get_library_manager()
    assert isinstance(manager, LibraryManager)

    with TemporaryDirectory(prefix="dep-subpipe-scope-") as temp_dir:
        dep_dir = Path(temp_dir) / "dep"
        dep_dir.mkdir()
        resolved_dep = build_resolved_dep(dep_dir, exported_pipe_codes=None)

        bare_library_id, bare_library = manager.open_library()
        with scoped_current_library(library_id=bare_library_id):
            manager._load_single_dependency(library=bare_library, resolved_dep=resolved_dep)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        report(title="host declares nothing", library=bare_library, library_id=bare_library_id)

        host_file = Path(temp_dir) / "host.mthds"
        host_file.write_text(HOST_COLLIDING_MTHDS, encoding="utf-8")
        colliding_library_id, colliding_library = manager.open_library()
        with scoped_current_library(library_id=colliding_library_id):
            manager._load_single_dependency(library=colliding_library, resolved_dep=resolved_dep)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        # load_from_blueprints validates the whole library, dependency entries included — since the
        # strict lookup landed, that validation raises here. The host pipe is registered before the
        # validation runs, so the shape-2 library is intact; catch and keep measuring.
        try:
            manager.load_from_blueprints(
                library_id=colliding_library_id,
                blueprints=[MthdsParser.make_pipelex_bundle_blueprint(bundle_path=host_file)],
            )
        except BaseException as exc:  # ruff: ignore[blind-except] - naming *which* error escapes IS the measurement here
            print(f"\n   load_from_blueprints(host) -> {type(exc).__name__}: {exc}")
        report(title="host declares its OWN pipe under the same bare code", library=colliding_library, library_id=colliding_library_id)

        # The published shape: a manifest exporting only the entry pipe.
        exporting_dep = build_resolved_dep(dep_dir, exported_pipe_codes={"probe_entry"})
        exporting_library_id, exporting_library = manager.open_library()
        with scoped_current_library(library_id=exporting_library_id):
            manager._load_single_dependency(library=exporting_library, resolved_dep=exporting_dep)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        report(title="dependency manifest exports only the entry pipe", library=exporting_library, library_id=exporting_library_id)


if __name__ == "__main__":
    main()
