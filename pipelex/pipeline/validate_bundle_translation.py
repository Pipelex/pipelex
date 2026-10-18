"""The one translation of a bundle's load-time refusals into the ``ValidateBundleError`` verdict.

Every surface that loads a bundle and must answer with a verdict wraps its load in
:func:`translate_to_validate_bundle_error`: ``validate_bundle`` and ``validate_bundles_from_directory``,
``resolve_crate_from_contents``, the library loads of the ``validate`` commands, and the run path's
``acquire_library``, so a run refuses an invalid bundle with the same located items ``validate`` gives.
It lives in its own module, rather than beside ``validate_bundle``, because the run path's seams sit
below the validation service in the import graph (``validate_bundle`` → ``bundle_validator`` →
``execution_seams``), and both must reach the same translation.
"""

import tomllib
from collections.abc import Collection, Generator, Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple, cast

from pydantic import ValidationError

from pipelex.base_exceptions import ErrorDomain, PipelexError, SecurityError
from pipelex.config import get_config
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError, BundleResourcePathError
from pipelex.core.exceptions import DryRunFailureErrorData, PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import (
    PipeFactoryError,
    PipeLoadRefusalError,
    PipeOperatorModelChoiceError,
    PipeRunError,
    PipeValidationError,
    caller_refusal,
    refusal_detail,
)
from pipelex.core.validation import report_validation_error
from pipelex.errors.error_codes import ErrorCode, code_is_method_domain
from pipelex.errors.security_event import security_target_kind
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.exceptions import LibraryError, MethodTreeLoadError
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.libraries.method_trees import bundle_files_under, reporting_host_library_tree_faults
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.handle_pipe_errors import (
    categorize_pipe_factory_error,
    categorize_pipe_operator_model_choice_error,
    categorize_pipe_validation_error,
    categorize_pipe_validation_with_libraries_error,
)
from pipelex.pipe_run.exceptions import DryRunError, DryRunGraphNotProducedError
from pipelex.pipeline.exceptions import HostLibraryLoadRefusalError, ValidateBundleError
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.typing.module_inspector import convert_file_path_to_module_path

# What a verdict's message reads where it named a file of the host's own library directories.
HOST_LIBRARY_FILE_PLACEHOLDER = "<host library file>"


def _backfill_pipe_error_source(pipe_error: PipeValidationError) -> None:
    """Backfill ``file_path`` on a pipe-channel error from the library manager's pipe-source map.

    Raise sites (``PipeAbstract`` input checks, ``PipeSequence`` output checks) don't know their
    file — pipes deliberately carry no source; provenance lives in the crate's ``source_map``,
    mirrored into the current library's source map during load, *before* ``validate_library``
    runs. Intercepting once at this catch boundary covers every raise site, present and future.

    Lookup is by the full ``domain.pipe_code`` ref only — never the bare-code suffix fallback
    (under the strict own-domain resolution rule, a bare-code suffix match would guess a file
    where the qualified ref did not resolve). A miss leaves ``file_path`` as ``None``: the fix stays source-less and
    falls under the conservative single-file rule, which is the safe direction.
    """
    if pipe_error.file_path is not None:
        return
    if pipe_error.domain_code is None or pipe_error.pipe_code is None:
        return
    source = get_library_manager().get_pipe_source(f"{pipe_error.domain_code}.{pipe_error.pipe_code}")
    if source is not None:
        # Compatibility boundary: injected managers written against the previous protocol may
        # still return ``Path``. Normalize before assigning to the string-only error model.
        pipe_error.file_path = str(source)


@contextmanager
def translate_to_validate_bundle_error() -> Generator[None, None, None]:
    """Translate the bundle-loading exception surface into a single ``ValidateBundleError``.

    Single source of truth for the bundle-loading error cascade, shared by the
    bundle-loading entry points: ``validate_bundle``, ``validate_bundles_from_directory``,
    ``pipelex.pipeline.resolve_bundle.resolve_crate_from_contents``, the library loads and
    dry-run sweeps of the ``validate pipe`` / ``validate --all`` commands, and the run path's
    ``pipelex.pipeline.execution_seams.acquire_library``, so running an invalid bundle is refused with
    the same items validating it gives.
    A ``MthdsParserError`` becomes a ``ValidateBundleError`` carrying the
    blueprint validation errors, a ``PipeFactoryError`` carries the categorized
    factory error, etc. Sharing one source of truth means a new handler only
    needs to be added once.

    **Every refusal of the method is a verdict, and only a refusal of the method.** After the class-specific
    arms, a final arm turns any other ``PipelexError`` whose code is the method's (its registry domain is
    ``method``) into a verdict with one item, so a refusal nobody wrote an arm for still reaches the author
    as an invalid bundle rather than as a crash or a no-verdict fault. A dry run's failures, and a library's
    refusal, become a verdict only when at least one of them is the method's: a failure whose every fault
    belongs to another actor, the runtime's own included, answers its own code, never that the method is
    invalid. A failure of the tool or its environment, a refusal of another actor than the method's author,
    anything that is not a ``PipelexError``, propagates as no verdict, along with the refusals that must
    keep their own class: ``PipeNotFoundError`` (its dedicated not-found handler), a security refusal, a
    ``SecurityError`` or any refusal coded in a security family (never absorbed by a domain handler, even
    when its code is the method's, as ``security.method_path_refused`` is), a ``ValidateBundleError``
    already produced (never re-wrapped), and a ``BundleResourceNotNamedError`` or a
    ``BundleResourcePathError``, which refuse the files submitted with the bundle rather than the bundle.
    """
    try:
        yield
    except MthdsParserError as parser_error:
        raise ValidateBundleError(
            message=parser_error.message,
            pipelex_bundle_blueprint_validation_errors=parser_error.validation_errors,
        ) from parser_error
    except PipeFactoryError as factory_error:
        factory_error_data = categorize_pipe_factory_error(factory_error=factory_error)
        raise ValidateBundleError(
            message=f"Pipe factory error: {factory_error}",
            pipe_factory_errors=[factory_error_data],
        ) from factory_error
    # Cascade order: ``except PipeValidationError`` must precede
    # ``except ValidationError``. Their sibling-under-``ValueError``
    # relationship (``PipeValidationError(ValueError)``, not a subclass of
    # ``pydantic.ValidationError``) is pinned by
    # ``tests/unit/pipelex/pipeline/test_validate_bundle_helper.py``.
    except PipeValidationError as pipe_error:
        _backfill_pipe_error_source(pipe_error)
        pipe_error_data = categorize_pipe_validation_with_libraries_error(pipe_error=pipe_error)
        raise ValidateBundleError(
            message=f"Pipe validation failed: {pipe_error}",
            pipe_validation_errors=[pipe_error_data],
        ) from pipe_error
    except ValidationError as validation_error:
        pipe_validation_errors = categorize_pipe_validation_error(validation_error=validation_error)
        validation_error_msg = report_validation_error(validation_error=validation_error).message
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error
    except PipeNotFoundError:
        # The base class on purpose: the slice miss raised by ``_pipes_to_dry_run`` is the
        # INPUT-domained ``EntryPipeNotFoundError`` subclass, and this arm must let it through raw,
        # domain and all. PipeNotFoundError is a PipeLibraryError (hence a LibraryError), but it is
        # NOT a bundle merge/load failure: it means a requested --pipe slice names a pipe absent from
        # the bundle. It has its own dedicated CLI handler (execute_validate's
        # `except PipeNotFoundError`), so it must propagate raw rather than be folded into a
        # ValidateBundleError by the arm below.
        raise
    except LibraryError as library_error:
        # Library merge / load failures that are NOT pydantic ValidationErrors: undeclared
        # cross-file concept references (ConceptLibraryError), signature/concrete contract
        # mismatches and duplicate concept/pipe refs (ConceptLibraryError / PipeLibraryError), and
        # the structured LibraryLoadingError aggregate (concept cycles, reserved-domain
        # violations, factory failures). Surface them as a clean ValidateBundleError instead of a
        # raw traceback. A LibraryError carries the blueprint- and pipe/concept-validation errors it was raised with;
        # forward them so the CLI renders the same structured detail it does for the other arms.
        # A library error that is not the method's, such as an invariant of the library manager
        # (`runtime.unexpected`) or library directories configured wrongly (`pipelex.config.invalid`), is no
        # verdict about the bundle, and propagates as it is, as does a security refusal.
        if not _code_makes_a_verdict(code=library_error.resolve_error_code()):
            raise
        raise ValidateBundleError(
            message=library_error.message,
            pipelex_bundle_blueprint_validation_errors=library_error.blueprint_validation_errors or None,
            pipe_validation_errors=library_error.pipe_concept_validation_errors or None,
        ) from library_error
    except PipeRunError as pipe_run_error:
        # A pipe run failing outside the sweep's per-pipe classification: one dry-run item on its pipe when
        # its fault is the method's, whose text is the sentence its code renders for the caller who reads the
        # verdict, and otherwise the fault itself, which no verdict carries, a security refusal it wraps included.
        failure_code = pipe_run_error.resolve_error_code()
        if not _code_makes_a_verdict(code=failure_code):
            raise
        failure_problem = caller_refusal(refusal=pipe_run_error, pipe_code=pipe_run_error.pipe_code)
        failure_params = failure_problem.params.as_wire() if failure_problem.params is not None else None
        raise ValidateBundleError(
            message=pipe_run_error.message,
            dry_run_failures=[
                DryRunFailureErrorData(
                    code=failure_code,
                    pipe_code=pipe_run_error.pipe_code,
                    message=f"Pipe '{pipe_run_error.pipe_code}' failed its dry run: {failure_problem.detail}",
                    params=failure_params or None,
                )
            ],
        ) from pipe_run_error
    except DryRunGraphNotProducedError:
        # A graph-producing dry run that produced none is a fault of its entrypoint, not of the bundle.
        raise
    except DryRunError as dry_run_error:
        # The sweep's failures, one per failing pipe, located at the innermost pipe that failed. A
        # DryRunError raised elsewhere carries none, and stands for one failure, its own. They are a verdict
        # only when one of them is the method's and none is a security refusal; otherwise the dry run's fault
        # answers its own code, a security refusal's first (`DryRunError.own_error_code`), every failure riding
        # its items, and never reads as an invalid method.
        dry_run_failures = dry_run_error.failures or [
            DryRunFailureErrorData(code=dry_run_error.resolve_error_code(), message=refusal_detail(refusal=dry_run_error))
        ]
        if any(security_target_kind(code=failure.code) is not None for failure in dry_run_failures):
            raise
        if not any(_code_makes_a_verdict(code=failure.code) for failure in dry_run_failures):
            raise
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_failures=dry_run_failures,
        ) from dry_run_error
    except PipeOperatorModelChoiceError as model_choice_error:
        # A pipe names a model its deck does not define: the operator located it on the pipe and the
        # field, and the library load added the file, so it becomes one `unknown_model` item carrying
        # the reference as written, the model type and the deck's suggestions. A model a catalog of this
        # deployment knows, which no enabled backend serves (`model.unavailable`), is no fault of the
        # method: it leaves as it is, located on the pipe and the field, whose fix is the deployment's.
        if not _code_makes_a_verdict(code=model_choice_error.resolve_error_code()):
            raise
        raise ValidateBundleError(
            message=model_choice_error.message,
            pipe_validation_errors=[categorize_pipe_operator_model_choice_error(model_choice_error=model_choice_error)],
        ) from model_choice_error
    except (ValidateBundleError, SecurityError, BundleResourceNotNamedError, BundleResourcePathError):
        # All are PipelexErrors the general arm below would otherwise catch. A verdict already produced
        # (e.g. by a nested load) passes through as it is: re-wrapping it would flatten its items into one.
        # A security refusal is never absorbed into a domain answer, verdict included. A file submitted with
        # the bundle that none of its steps names, or files read at load too large to travel with it, are a
        # refusal of the request, not of the bundle, so they keep their own class rather than becoming a
        # verdict about a bundle that may well be valid.
        raise
    except PipelexError as refusal:
        verdict = _make_refusal_verdict(refusal=refusal)
        if verdict is None:
            raise
        raise verdict from refusal


@contextmanager
def reporting_host_library_faults() -> Generator[None, None, None]:
    """Report a fault of loading this host's own library directories as the deployment's, never as the caller's input.

    Around a load of library directories that are not the caller's (`library_dirs_are_callers` False), such as the
    ones a server loads beside a request's bundles. A tree that cannot be listed, or whose requirements refuse it,
    leaves as `reporting_host_library_tree_faults` reports it. Any other refusal that would be the caller's input in
    the caller's own content (an `input`-domained `PipelexError`, such as a pipe factory's refusal or an unknown
    model, or a pydantic `ValidationError` of a blueprint) leaves as a `HostLibraryLoadRefusalError`, which the
    validation translation lets through as no verdict. A security refusal keeps its own class, as everywhere.

    Raises:
        HostLibraryLoadRefusalError: A method of the directories refused to load.
        HostLibraryTreeError: A tree of the directories could not be listed.
        HostLibraryRequirementsError: A method of the directories declares requirements its environment refuses.
    """
    try:
        with reporting_host_library_tree_faults():
            yield
    except SecurityError:
        raise
    except ValidationError as validation_error:
        msg = f"A method in a library directory of this host does not validate: {report_validation_error(validation_error=validation_error).message}"
        raise HostLibraryLoadRefusalError(msg) from validation_error
    except PipelexError as refusal:
        if not ErrorDomain.from_problem_domain(refusal.resolve_domain()).is_input:
            raise
        msg = f"A method in a library directory of this host refuses to load ({type(refusal).__name__}): {refusal.message}"
        raise HostLibraryLoadRefusalError(msg) from refusal


def _code_makes_a_verdict(*, code: ErrorCode) -> bool:
    """Whether a refusal coded so is a verdict about the bundle: its code is the method's, and no security refusal's.

    Every arm of the translation asks it, so a security refusal, many of which the method's author acts on
    (``security.method_path_refused``, ``security.template_refused``), keeps its code and its security event on
    whichever error carries it, never becoming a verdict's item.
    """
    return code_is_method_domain(code=code) and security_target_kind(code=code) is None


def _make_refusal_verdict(*, refusal: PipelexError) -> ValidateBundleError | None:
    """The one-item verdict for a refusal of the caller's input that has no arm of its own, else ``None``.

    ``None`` — no verdict — unless the refusal's code is the method's: a refusal another actor must act on,
    the caller's input, the account, the operator or the runtime, is never the bundle's fault, and keeps
    its own code. A security refusal has no verdict either, whatever its class or its domain: a refusal
    coded in a security family, such as a step's template file that climbs out of its method tree
    (``security.method_path_refused``), keeps its code and logs its security event, never a verdict's.

    The item is ``pipe_validation`` when the library load located the refusal on the pipe it was building
    (``PipeLoadRefusalError``, with the pipe's code, domain and file), and ``blueprint_validation`` otherwise.
    It carries no ``error_type``: a refusal with a closed code has its own arm above, and naming one here
    would claim a diagnosis the refusal does not make.

    The item's text is the sentence the refusal's code renders for a caller, never the refusal's own message:
    the verdict is read by the caller, and the message is the operator's diagnostics.
    """
    if not _code_makes_a_verdict(code=refusal.resolve_error_code()):
        return None
    message = refusal_detail(refusal=refusal)
    if isinstance(refusal, PipeLoadRefusalError):
        return ValidateBundleError(
            message=message,
            pipe_validation_errors=[
                PipesAndConceptValidationErrorData(
                    pipe_code=refusal.pipe_code,
                    domain_code=refusal.domain_code,
                    source=refusal.source,
                    message=message,
                    field_path="",
                )
            ],
        )
    return ValidateBundleError(
        message=message,
        pipelex_bundle_blueprint_validation_errors=[PipelexBundleBlueprintValidationErrorData(message=message)],
    )


@contextmanager
def withholding_host_library_files(
    *, library_dirs: Sequence[Path], caller_sources: Collection[str] = (), caller_contents: Collection[str] = ()
) -> Generator[None, None, None]:
    """Keep the files of a host's own library directories out of the verdict the block raises.

    A verdict is read by the caller, its items' messages and locators included, so it must not name a path on the
    host. When submitted content is validated or run, the library
    directories loaded beside it are the host's (installed libraries, the defaults, ``PIPELEXPATH``), and an item
    located in one of their files would name that file, as would a message about it, such as a duplicate
    declaration, a load that failed, or two ``@pipe_func`` functions of the same name, which the registry names by
    a module name spelled from the file's absolute path. Around such a load, a ``ValidateBundleError`` leaves this
    block with every one of those names taken out: the item carries no ``source``, still located by its pipe and
    domain, and a message reads ``HOST_LIBRARY_FILE_PLACEHOLDER`` where it named one, while the item of a host file that
    restates a name conflict an item of the caller's own file reports is left out. The names are the ones the
    load gives: each bundle file in the spelling it gives a bundle's ``source`` and resolved, and each Python file's
    module name. A name the caller submitted as a content's source (``caller_sources``) is the caller's own and is
    never withheld, even where a host file is spelled the same. The template files the host's ``PipeDocGen`` steps
    name are withheld too, in the spelling the steps give them, since their refusals, at load or in the dry run of a
    caller's pipe that runs one, name them; a template file the caller's own content names (``caller_contents``)
    stays, so the caller's own steps keep naming theirs.

    A bundle validated from a file on the caller's own disk, or validated or run with library directories that
    are the caller's, keeps every path: there the directories are the caller's to read. A package the content
    depends on by address never needs this, since its bundles are named by the package's address at load.
    """
    try:
        yield
    except ValidateBundleError as verdict:
        host_files = _host_library_files(library_dirs=library_dirs)
        host_library_names = host_files.names - set(caller_sources)
        host_library_names |= host_files.template_files - _template_files_named_in(mthds_texts=caller_contents)
        if not host_library_names:
            raise
        withheld_verdict = verdict.withholding_files(withheld_files=host_library_names, placeholder=HOST_LIBRARY_FILE_PLACEHOLDER)
        # The withheld verdict takes this one's place over the same cause, so its report inherits the same
        # classification and the unwithheld verdict is not left on the chain beside it.
        raise withheld_verdict from verdict.__cause__


def _template_files_named_in(*, mthds_texts: Iterable[str]) -> set[str]:
    """The ``template_file`` every pipe of the given bundle texts names, read from the TOML alone.

    The bundles are read as TOML rather than parsed into blueprints, because the bundle whose refusal is being
    withheld may be the one that does not parse, and its steps' template files are still the ones its messages name.
    """
    template_files: set[str] = set()
    for mthds_text in mthds_texts:
        try:
            document = tomllib.loads(mthds_text)
        except tomllib.TOMLDecodeError:
            continue
        pipe_tables: object = document.get("pipe")
        if not isinstance(pipe_tables, dict):
            continue
        for pipe_table in cast("dict[str, object]", pipe_tables).values():
            if not isinstance(pipe_table, dict):
                continue
            template_file = cast("dict[str, object]", pipe_table).get("template_file")
            if isinstance(template_file, str):
                template_files.add(template_file)
    return template_files


def _bundle_text_or_none(*, library_file: Path) -> str | None:
    """A host bundle file's text, or None for a file the load could not read either, whose refusal names no template file."""
    try:
        return library_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class _HostLibraryFiles(NamedTuple):
    """What a verdict must not name of the host's library directories."""

    names: set[str]
    """Every name the library load gives a file of the directories."""

    template_files: set[str]
    """The template files the steps of their bundles name, as the steps spell them."""


def _host_library_files(*, library_dirs: Sequence[Path]) -> _HostLibraryFiles:
    """Every name the library load gives a file of ``library_dirs``, and the template files their steps name, in one walk.

    A bundle file is named as listed, which is the ``source`` the load gives it, and resolved; a Python file by
    the module name the function registry imports it under, which is spelled from its resolved path. Each bundle file
    is read once, for the template files its steps name.
    """
    names: set[str] = set()
    host_texts: list[str] = []
    library_files: list[Path]
    try:
        library_files = get_pipelex_mthds_files_from_dirs(set(library_dirs))
    except MethodTreeLoadError:
        # This runs while a verdict is being withheld, and the load listed these trees a moment ago: a listing that
        # fails now must never take the verdict's place, so every bundle file under the directories is withheld, a
        # superset of the names the load gave.
        library_files = bundle_files_under(library_dirs=library_dirs)
    for library_file in library_files:
        names.add(str(library_file))
        host_text = _bundle_text_or_none(library_file=library_file)
        if host_text is not None:
            host_texts.append(host_text)
        try:
            names.add(str(library_file.resolve()))
        except (OSError, RuntimeError):
            # The load names such a file by its listed spelling only (see ``LibraryManager.load_libraries``).
            continue
    for library_dir in library_dirs:
        if not library_dir.is_dir():
            continue
        for python_file in find_files_in_dir(dir_path=library_dir, pattern="*.py", excluded_dirs=list(get_config().interpreter.scan.excluded_dirs)):
            try:
                names.add(convert_file_path_to_module_path(python_file))
            except (OSError, RuntimeError):
                continue
    return _HostLibraryFiles(names=names, template_files=_template_files_named_in(mthds_texts=host_texts))
