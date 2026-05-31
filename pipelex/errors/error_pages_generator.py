"""Generator for the per-class error documentation pages.

Each non-test :class:`pipelex.base_exceptions.PipelexError` subclass gets a
markdown page at ``docs/errors/<kebab-class-name>.md``, named so the path
aligns with :meth:`PipelexError.type_uri`'s final segment. The docs site can
then host those pages at ``<base_uri>/<kebab-class-name>`` and a clickable
RFC 7807 ``type`` URI lands the user on a populated reference page.

Pages a maintainer has hand-edited are protected by an ``<!-- pipelex:authored -->``
HTML comment anywhere in the file: when the generator detects it on an
existing page, the page is left untouched. Generated pages carry a different
marker (``<!-- pipelex:generated -->``) so a quick ``grep`` distinguishes the
two populations.
"""

from __future__ import annotations

import functools
import importlib
import sys
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic.dataclasses import dataclass

import pipelex
from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction
from pipelex.tools.misc.string_utils import pascal_case_to_kebab

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


_PIPELEX_ROOT = Path(pipelex.__file__).resolve().parent
_FIXTURE_DIR_NAMES = frozenset({"test_extras", "test_helpers"})


@functools.cache
def _force_load_all_error_modules() -> None:
    """Force-import every ``exceptions.py`` / ``*_exceptions.py`` module under ``pipelex/``.

    Cached via :func:`functools.cache` so the first call walks the package and
    ``importlib.import_module``-s every properly-named error module while
    subsequent calls are no-ops. Two preconditions keep this safe and complete,
    both enforced by
    ``tests/unit/pipelex/errors/test_error_class_location_convention.py``:

    1. Every :class:`PipelexError` subclass lives in a module named
       ``exceptions.py`` or ``<topic>_exceptions.py`` (the Phase 6 file-naming
       convention). A name-filtered ``rglob`` therefore captures the complete
       error-class set — no allowlist needed.
    2. Every properly-named error module imports only base error classes
       (``PipelexError`` / ``CogtError`` / ``CredentialsError`` /
       ``ClickException``) — no third-party SDK pulls. Force-loading adds no
       optional-plugin weight to pytest collection or dev CLI invocations.

    Called by :func:`iter_pipelex_error_subclasses` so the docs generator and
    the type-URI uniqueness test see every subclass — including those whose
    home module is otherwise reached only by a deferred plugin / factory
    import path. Production code (notably ``Pipelex.make()``) does NOT touch
    this — discovery has no runtime side effect outside the dev/test-time
    consumers.

    Per-module import failures are accumulated and raised once at the end so a
    single broken ``*_exceptions.py`` surfaces with its dotted module name
    rather than aborting the walk under an opaque exception whose traceback
    frames all live inside this helper. ``functools.cache`` only memoizes the
    success path (no caching on exception), so a fix-then-retry cycle inside
    a long-lived dev session works without ``cache_clear()``.

    The catch is intentionally broad: ``importlib.import_module`` runs the
    target module's top-level code, so a typo or bad reference inside a new
    ``*_exceptions.py`` can surface as ``NameError``, ``SyntaxError``,
    ``AttributeError``, … — all of which must be aggregated like ``ImportError``
    so the dev sees the full list of broken modules at once.

    To clear the cache (e.g. inside a long-lived dev session after adding a
    new ``*_exceptions.py``), call ``_force_load_all_error_modules.cache_clear()``.
    """
    failures: list[tuple[str, BaseException]] = []
    for path in sorted(_PIPELEX_ROOT.rglob("*.py")):
        name = path.name
        if name != "exceptions.py" and not name.endswith("_exceptions.py"):
            continue
        rel = path.relative_to(_PIPELEX_ROOT.parent).with_suffix("")
        dotted = ".".join(rel.parts)
        try:
            importlib.import_module(dotted)
        except Exception as exc:  # noqa: BLE001
            # importlib runs the target module's top-level code — an open-ended exception surface
            # (NameError, SyntaxError, …) that must be aggregated like ImportError so the dev
            # sees the full list of broken modules at once instead of aborting on the first one.
            failures.append((dotted, exc))
    if failures:
        lines = ["One or more error modules failed to import during discovery:"]
        lines.extend(f"  - {name}: {exc}" for name, exc in failures)
        msg = "\n".join(lines)
        # Chain from the first failure so the dev sees a full traceback (file:line
        # of the broken module) in addition to the aggregated list of names —
        # str(exc) alone elides where the failure happened.
        raise RuntimeError(msg) from failures[0][1]


def _is_production_subclass(cls: type[PipelexError]) -> bool:
    """True when ``cls`` should appear in the production discovery set.

    Excludes synthetic subclasses created inside test modules (``tests.*``) and
    classes defined inside shipped fixture packages (``pipelex/.../test_extras/``,
    ``pipelex/.../test_helpers/``) — those are test infrastructure that happens
    to be packaged alongside production code so it can be reused across
    downstream test suites.
    """
    if cls.__module__.startswith("tests."):
        return False
    module = sys.modules.get(cls.__module__)
    if module is None:
        return True
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        return True
    try:
        rel = Path(module_file).resolve().relative_to(_PIPELEX_ROOT)
    except ValueError:
        return True
    return _FIXTURE_DIR_NAMES.isdisjoint(rel.parts)


def iter_pipelex_error_subclasses() -> Iterator[type[PipelexError]]:
    """Yield :class:`PipelexError` and every loaded subclass, breadth-first.

    Calls :func:`_force_load_all_error_modules` first so deferred-import
    plugin / factory error modules are reachable via ``__subclasses__()``. The
    call is idempotent — first invocation walks the filesystem, subsequent
    invocations are no-ops.

    Skips classes that fail :func:`_is_production_subclass` so synthetic
    subclasses created by other tests in the same pytest session and classes
    defined under shipped fixture packages (``pipelex/.../test_extras/`` /
    ``test_helpers/``) never leak into the generated docs or the smoke-test
    assertions.
    """
    _force_load_all_error_modules()
    seen: set[type[PipelexError]] = set()
    stack: list[type[PipelexError]] = [PipelexError]
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if _is_production_subclass(cls):
            yield cls
        stack.extend(cls.__subclasses__())


# Marker a maintainer adds to a generated page to claim it for hand-editing.
# When present, :func:`generate_error_pages` skips the page on regeneration.
AUTHORED_MARKER = "<!-- pipelex:authored -->"
# Marker stamped on every generated page so the two populations are
# distinguishable at a glance (``grep -L pipelex:authored docs/errors``).
GENERATED_MARKER = "<!-- pipelex:generated -->"
# Stem of the landing page emitted alongside the per-class pages. Kept in nav;
# the per-class pages are declared ``not_in_nav`` in ``mkdocs.yml`` so the
# sidebar does not balloon with one entry per error class.
INDEX_STEM = "index"


@dataclass(frozen=True)
class ErrorPagesReport:
    """Outcome summary returned by :func:`generate_error_pages`.

    Carries the four populations the CLI command reports back:
    ``written`` (a page was newly created or refreshed),
    ``unchanged`` (a generated page already on disk was byte-identical),
    ``preserved`` (the file carried :data:`AUTHORED_MARKER` and was left as-is),
    ``removed`` (a previously-generated page no longer maps to a target class
    and was deleted; pages bearing :data:`AUTHORED_MARKER` are never removed
    and surface as ``preserved`` instead).

    ``frozen`` only blocks rebinding the fields — the lists are still populated
    in place via ``.append`` by ``_commit_page`` / ``_remove_orphans``.
    """

    written: list[Path] = field(default_factory=list[Path])
    unchanged: list[Path] = field(default_factory=list[Path])
    preserved: list[Path] = field(default_factory=list[Path])
    removed: list[Path] = field(default_factory=list[Path])

    @property
    def total(self) -> int:
        return len(self.written) + len(self.unchanged) + len(self.preserved) + len(self.removed)


def page_slug(cls: type[PipelexError]) -> str:
    """Return the kebab-case slug used both as the file stem and as the URI tail."""
    return pascal_case_to_kebab(cls.__name__)


def render_error_page(cls: type[PipelexError]) -> str:
    """Render the default markdown body for ``cls``.

    Includes the class identity (title, type URI, defining module), the
    declared error domain (or ``(inherited from parent)`` for subclasses that
    don't override it), a link to the parent class's page when the parent is
    itself a ``PipelexError``, and a back-link to the Error Model overview.
    """
    title = cls.title()
    type_uri = cls.type_uri()
    domain_value = _resolve_class_level_domain(cls)
    parent_link = _parent_link(cls)
    description = f"Reference for the `{cls.__name__}` Pipelex error class."

    rows: list[tuple[str, str]] = [
        ("`error_type`", f"`{cls.__name__}`"),
        ("`title`", title),
        ("`type_uri`", f"`{type_uri}`"),
        ("`error_domain`", domain_value),
        ("Defined in", f"`{cls.__module__}`"),
        ("Parent class", parent_link),
    ]
    declared_action = _resolve_class_level_user_action(cls)
    if declared_action is not None:
        rows.append(("`user_action`", declared_action))
    docstring = _short_docstring(cls)

    lines: list[str] = [
        "---",
        f'title: "{title}"',
        f'description: "{description}"',
        "---",
        "",
        f"{GENERATED_MARKER}",
        "",
        f"# {title}",
        "",
    ]
    if docstring is not None:
        lines.extend([docstring, ""])
    lines.extend(
        [
            "| Field | Value |",
            "|---|---|",
            *(f"| {key} | {value} |" for key, value in rows),
            "",
            "[Back to Error Model overview](../under-the-hood/error-model.md)",
            "",
        ]
    )
    return "\n".join(lines)


def generate_error_pages(
    output_dir: Path,
    classes: Iterable[type[PipelexError]] | None = None,
) -> ErrorPagesReport:
    """Write one markdown page per :class:`PipelexError` subclass into ``output_dir``.

    ``classes`` defaults to every loaded production subclass via
    :func:`iter_pipelex_error_subclasses`. Pages bearing :data:`AUTHORED_MARKER`
    are left untouched and reported under ``preserved``; pages whose generated
    content matches what's already on disk are reported as ``unchanged`` (no
    write, no mtime churn). Pre-existing generated pages whose slug no longer
    appears in ``target_classes`` are deleted and reported under ``removed`` —
    pages with :data:`AUTHORED_MARKER` are never removed, the index page is
    never removed.

    Raises a loud ``RuntimeError`` if two target classes resolve to the same
    kebab slug (e.g. ``LLMError`` and ``LlmError`` both kebab to ``llm-error``),
    so the collision is caught at generation time instead of silently — the
    second page would overwrite the first.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target_classes = list(classes) if classes is not None else list(iter_pipelex_error_subclasses())

    slug_owners: dict[str, type[PipelexError]] = {}
    for cls in target_classes:
        slug = page_slug(cls)
        previous = slug_owners.get(slug)
        if previous is not None and previous is not cls:
            msg = (
                f"Kebab-slug collision on {slug!r}: {previous.__module__}.{previous.__name__} "
                f"and {cls.__module__}.{cls.__name__} both resolve to the same docs page. "
                "Rename one class — acronym-casing variants (e.g. LLMError / LlmError) kebab "
                "to the same slug."
            )
            raise RuntimeError(msg)
        slug_owners[slug] = cls

    report = ErrorPagesReport()
    expected_stems: set[str] = {page_slug(cls) for cls in target_classes} | {INDEX_STEM}
    for cls in target_classes:
        target = output_dir / f"{page_slug(cls)}.md"
        _commit_page(target, render_error_page(cls), report)

    index_target = output_dir / f"{INDEX_STEM}.md"
    _commit_page(index_target, render_index_page(target_classes), report)

    _remove_orphans(output_dir=output_dir, expected_stems=expected_stems, report=report)

    return report


def _remove_orphans(output_dir: Path, expected_stems: set[str], report: ErrorPagesReport) -> None:
    """Delete generated ``.md`` files whose stem is not in ``expected_stems``.

    Files carrying :data:`AUTHORED_MARKER` are preserved verbatim — those
    pages have been hand-claimed and the maintainer is responsible for their
    lifecycle. Files with no marker at all (neither generated nor authored)
    are left alone too, since this function only takes responsibility for
    pages this generator previously wrote.
    """
    for path in output_dir.glob("*.md"):
        if path.stem in expected_stems:
            continue
        content = path.read_text(encoding="utf-8")
        if has_authored_marker(content):
            report.preserved.append(path)
            continue
        if GENERATED_MARKER not in content:
            continue
        path.unlink()
        report.removed.append(path)


def _commit_page(target: Path, new_content: str, report: ErrorPagesReport) -> None:
    """Apply the write / unchanged / preserved classification to one target path."""
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if has_authored_marker(existing):
            report.preserved.append(target)
            return
        if existing == new_content:
            report.unchanged.append(target)
            return
    target.write_text(new_content, encoding="utf-8")
    report.written.append(target)


def render_index_page(classes: Iterable[type[PipelexError]]) -> str:
    """Render the landing page that lists every per-class error page.

    Pages are grouped by the top-level :class:`PipelexError` branch they belong
    to (e.g. ``CogtError``, ``PipelineExecutionError``, ``TemporalFlowError``)
    so readers can find a class without scrolling the full alphabetical list.
    """
    sorted_classes = sorted(classes, key=lambda c: c.__name__)
    by_branch: dict[str, list[type[PipelexError]]] = {}
    for cls in sorted_classes:
        branch_label = _top_level_branch_label(cls)
        by_branch.setdefault(branch_label, []).append(cls)

    lines: list[str] = [
        "---",
        'title: "Error Reference"',
        'description: "Auto-generated reference index — one page per Pipelex error class."',
        "---",
        "",
        f"{GENERATED_MARKER}",
        "<!-- This index is generated by `pipelex-dev generate-error-pages`. Add the",
        f"     `{AUTHORED_MARKER}` marker anywhere on the page to claim it for",
        "     hand-editing — the generator will then preserve it on every run. -->",
        "",
        "# Error Reference",
        "",
        "Every Pipelex error class has a stable RFC 7807 `type` URI on the form",
        "`<base_uri>/<kebab-class-name>/`, and that URI dereferences to one of the pages",
        "below. The list is grouped by the top-level branch a class belongs to so the",
        "structural shape of the hierarchy stays visible.",
        "",
        "See [Error Model](../under-the-hood/error-model.md) for the underlying contract,",
        "classification rules, and the cross-boundary Temporal bridge.",
        "",
    ]
    for branch in sorted(by_branch):
        lines.append(f"## {branch}")
        lines.append("")
        for cls in by_branch[branch]:
            lines.append(f"- [`{cls.__name__}`]({page_slug(cls)}.md) — {cls.title()}")
        lines.append("")
    return "\n".join(lines)


def _top_level_branch_label(cls: type[PipelexError]) -> str:
    """Return a stable grouping label for the index — name of the direct ``PipelexError`` child ancestor.

    Multi-base subclasses (rare in this hierarchy) are grouped under their
    first ``PipelexError`` base — ``__bases__[0]`` wins. The grouping is
    cosmetic, so first-base-wins is fine; the per-class page still links to
    its actual first parent which preserves the structural ambiguity.
    """
    if cls is PipelexError:
        return "PipelexError (root)"
    current: type[PipelexError] = cls
    while True:
        parents = [base for base in current.__bases__ if issubclass(base, PipelexError)]
        if not parents:
            return current.__name__
        first_pipelex_parent = parents[0]
        if first_pipelex_parent is PipelexError:
            return current.__name__
        current = first_pipelex_parent


def has_authored_marker(content: str) -> bool:
    """Return True when :data:`AUTHORED_MARKER` appears as its own (stripped) line.

    A standalone-line check ensures the generator's own instructional text —
    which mentions the marker inside a longer HTML comment — does not falsely
    flag every generated page as hand-authored on the next run.
    """
    return any(line.strip() == AUTHORED_MARKER for line in content.splitlines())


def _resolve_class_level_domain(cls: type[PipelexError]) -> str:
    """Return the formatted ``error_domain`` value, or an inherited marker."""
    declared = cls.__dict__.get("error_domain")
    if isinstance(declared, ErrorDomain):
        return f"`{declared}`"
    if cls is PipelexError:
        return "_(unset)_"
    return "_(inherited from parent)_"


def _resolve_class_level_user_action(cls: type[PipelexError]) -> str | None:
    """Return a markdown rendering of the class-level :class:`UserAction`, or ``None``."""
    declared = cls.__dict__.get("user_action")
    if not isinstance(declared, UserAction):
        return None
    kind_repr = f"`{declared.kind}`"
    if declared.detail:
        return f"{kind_repr} — {declared.detail}"
    return kind_repr


def _parent_link(cls: type[PipelexError]) -> str:
    """Return a markdown link to the first ``PipelexError`` parent, or a plain ``Exception`` label."""
    parents = [base for base in cls.__bases__ if issubclass(base, PipelexError) and base is not cls]
    if not parents:
        return "`Exception` (Python builtin)"
    return f"[`{parents[0].__name__}`]({page_slug(parents[0])}.md)"


def _short_docstring(cls: type[PipelexError]) -> str | None:
    """Return the first non-empty paragraph of ``cls.__doc__``, if any."""
    raw = cls.__dict__.get("__doc__")
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    first_paragraph = stripped.split("\n\n", 1)[0]
    return " ".join(line.strip() for line in first_paragraph.splitlines() if line.strip())
