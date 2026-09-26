"""The one translation of a bundle's load-time refusals into the ``ValidateBundleError`` verdict.

Every surface that loads a bundle and must answer with a verdict wraps its load in
:func:`translate_to_validate_bundle_error`: ``validate_bundle`` and ``validate_bundles_from_directory``,
``resolve_crate_from_contents``, the library loads of the ``validate`` commands, and the run path's
``acquire_library``, so a run refuses an invalid bundle with the same located items ``validate`` gives.
It lives in its own module, rather than beside ``validate_bundle``, because the run path's seams sit
below the validation service in the import graph (``validate_bundle`` → ``bundle_validator`` →
``execution_seams``), and both must reach the same translation.
"""

from collections.abc import Generator
from contextlib import contextmanager

from pydantic import ValidationError

from pipelex.base_exceptions import PipelexError, SecurityError, error_domain_is_input
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import (
    PipeFactoryError,
    PipeLoadRefusalError,
    PipeOperatorModelChoiceError,
    PipeRunError,
    PipeValidationError,
    caller_facing_refusal_text,
)
from pipelex.core.validation import report_validation_error
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.exceptions import LibraryError, LibraryLoadingError
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.handle_pipe_errors import (
    categorize_pipe_factory_error,
    categorize_pipe_operator_model_choice_error,
    categorize_pipe_validation_error,
    categorize_pipe_validation_with_libraries_error,
)
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.registries.exceptions import FuncRegistryError


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

    **Every refusal of the bundle is a verdict.** After the class-specific arms, a final arm turns any
    other ``PipelexError`` whose report is ``input``-domained (the caller's fault) into a verdict with one
    item, so a refusal nobody wrote an arm for still reaches the author as an invalid bundle rather than
    as a crash or a no-verdict fault. Only a failure of the tool or its environment — a ``config`` or
    ``runtime`` fault, an unclassified one, anything that is not a ``PipelexError`` — propagates as
    no verdict, along with the refusals that must keep their own class: ``PipeNotFoundError`` (its
    dedicated not-found handler), a ``SecurityError`` (never absorbed by a domain handler), and a
    ``ValidateBundleError`` already produced (never re-wrapped).
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
        # raw traceback. LibraryLoadingError carries blueprint- and pipe/concept-validation errors;
        # forward them so the CLI renders the same structured detail it does for the other arms.
        if isinstance(library_error, LibraryLoadingError):
            blueprint_validation_errors = library_error.blueprint_validation_errors
            pipe_concept_validation_errors = library_error.pipe_concept_validation_errors
        else:
            blueprint_validation_errors = None
            pipe_concept_validation_errors = None
        raise ValidateBundleError(
            message=library_error.message,
            pipelex_bundle_blueprint_validation_errors=blueprint_validation_errors,
            pipe_validation_errors=pipe_concept_validation_errors,
        ) from library_error
    except FuncRegistryError as func_registry_error:
        # A duplicate @pipe_func name across the scanned library dirs. Raised while loading the
        # library, so it lands here rather than on the PipeFunc field validator's ValueError path.
        # It is caller-fixable input (rename one with @pipe_func(name=...)), so it must produce a
        # verdict — `is_valid: false` — not the "no verdict could be produced" exit 2 / 5xx an
        # untranslated error would give.
        raise ValidateBundleError(message=func_registry_error.message) from func_registry_error
    except PipeRunError as pipe_run_error:
        raise ValidateBundleError(
            message=pipe_run_error.message,
            dry_run_error_message=pipe_run_error.message,
        ) from pipe_run_error
    except DryRunError as dry_run_error:
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_error_message=dry_run_error.message,
        ) from dry_run_error
    except PipeOperatorModelChoiceError as model_choice_error:
        # A pipe names a model its deck does not define: the operator located it on the pipe and the
        # field, and the library load added the file, so it becomes one `unknown_model` item carrying
        # the reference as written, the model type and the deck's suggestions.
        raise ValidateBundleError(
            message=model_choice_error.message,
            pipe_validation_errors=[categorize_pipe_operator_model_choice_error(model_choice_error=model_choice_error)],
        ) from model_choice_error
    except (ValidateBundleError, SecurityError):
        # Both are PipelexErrors the general arm below would otherwise catch. A verdict already produced
        # (e.g. by a nested load) passes through as it is: re-wrapping it would flatten its items into one.
        # A security refusal is never absorbed into a domain answer, verdict included.
        raise
    except PipelexError as refusal:
        verdict = _make_refusal_verdict(refusal=refusal)
        if verdict is None:
            raise
        raise verdict from refusal


def _make_refusal_verdict(*, refusal: PipelexError) -> ValidateBundleError | None:
    """The one-item verdict for a refusal of the caller's input that has no arm of its own, else ``None``.

    ``None`` — no verdict — unless the refusal's report is ``input``-domained: a ``config`` or ``runtime``
    fault, or an unclassified one, is a failure of the tool or its environment, which the validator must
    not report as the bundle's fault. The item is ``pipe_validation`` when the library load located the
    refusal on the pipe it was building (``PipeLoadRefusalError``, with the pipe's code, domain and file),
    and ``blueprint_validation`` otherwise. It carries no ``error_type``: a refusal with a closed code
    has its own arm above, and naming one here would claim a diagnosis the refusal does not make.

    The item's text is the refusal's message only when that message was authored as caller-facing copy,
    and otherwise its title: the verdict is caller-facing as a whole and is kept verbatim under STRICT
    disclosure, so internal text must not ride it past the redaction it would otherwise get.
    """
    if not error_domain_is_input(refusal.to_error_report().error_domain):
        return None
    message = caller_facing_refusal_text(refusal=refusal)
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
