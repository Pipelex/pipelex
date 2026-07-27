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
    itself a ``PipelexError``, and a back-link to the Error Reference index.
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
            "[Back to Error Reference](index.md)",
            "",
        ]
    )
    return "\n".join(lines)


def generate_error_pages(
    *,
    output_dir: Path,
    classes: Iterable[type[PipelexError]] | None = None,
) -> ErrorPagesReport:
    """Write one markdown page per :class:`PipelexError` subclass into ``output_dir``.

    ``classes`` defaults to every loaded production subclass via
    :func:`iter_pipelex_error_subclasses`. Alongside the per-class pages it
    emits an ``index.md`` overview and one macro listing page per non-empty
    :data:`_MACRO_SECTIONS` area (the entries nested under "Error Reference" in
    the nav). Pages bearing :data:`AUTHORED_MARKER` are left untouched and
    reported under ``preserved``; pages whose generated content matches what's
    already on disk are reported as ``unchanged`` (no write, no mtime churn).
    Pre-existing generated pages whose slug no longer appears in
    ``target_classes`` (or a macro page that lost all its classes) are deleted
    and reported under ``removed`` — pages with :data:`AUTHORED_MARKER` are never
    removed, the index page is never removed.

    Raises a loud ``RuntimeError`` if two target classes resolve to the same
    kebab slug (e.g. ``LLMError`` and ``LlmError`` both kebab to ``llm-error``),
    or if a class slug collides with a generated listing-page stem (the index or
    a macro-area page), so either collision is caught at generation time instead
    of silently overwriting a page.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target_classes = list(classes) if classes is not None else list(iter_pipelex_error_subclasses())

    # Stems owned by the generated listing pages (the index + one per macro area). A
    # per-class page is committed first, then the listing pages to the same dir, so a
    # class whose slug lands here would have its reference page silently overwritten —
    # catch it loudly at generation time instead.
    reserved_stems = {INDEX_STEM, *(slug for slug, _ in _MACRO_SECTIONS)}
    slug_owners: dict[str, type[PipelexError]] = {}
    for cls in target_classes:
        slug = page_slug(cls)
        if slug in reserved_stems:
            msg = (
                f"Reserved-slug collision on {slug!r}: {cls.__module__}.{cls.__name__} kebabs to "
                "the stem of a generated listing page (the index or a macro-area page), whose "
                "content would overwrite the per-class page. Rename the class."
            )
            raise RuntimeError(msg)
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
        _commit_page(target=target, new_content=render_error_page(cls), report=report)

    # Macro listing pages — one per non-empty macro area. Their stems join
    # ``expected_stems`` so a macro that still has classes is never treated as an
    # orphan, while a macro that loses all its classes (none written this run)
    # falls through to ``_remove_orphans`` and is deleted like any stale page.
    by_subsystem = _group_by_subsystem(target_classes)
    for macro_slug, macro_heading in _MACRO_SECTIONS:
        sections = _subsystems_for_macro(macro_slug=macro_slug, by_subsystem=by_subsystem)
        if not sections:
            continue
        _commit_page(
            target=output_dir / f"{macro_slug}.md", new_content=render_macro_page(macro_heading=macro_heading, sections=sections), report=report
        )
        expected_stems.add(macro_slug)

    index_target = output_dir / f"{INDEX_STEM}.md"
    _commit_page(target=index_target, new_content=render_index_page(by_subsystem), report=report)

    _remove_orphans(output_dir=output_dir, expected_stems=expected_stems, report=report)

    return report


def _remove_orphans(output_dir: Path, *, expected_stems: set[str], report: ErrorPagesReport) -> None:
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


def _commit_page(*, target: Path, new_content: str, report: ErrorPagesReport) -> None:
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


# Macro sections — the top-level left-sidebar groups nested under "Error
# Reference" in ``mkdocs.yml``, in display order. ``(slug, heading)``. Each
# bundles several subsystems (see :data:`_SUBSYSTEM_SECTIONS`) onto one listing
# page so the nav shows a handful of macro areas instead of one flat entry.
# The slugs are the page stems (``errors/<slug>.md``) and MUST stay in sync with
# the nav block + ``not_in_nav`` re-includes in ``mkdocs.yml``.
_MACRO_SECTIONS: tuple[tuple[str, str], ...] = (
    ("authoring-and-language", "Authoring & language"),
    ("execution-and-runtime", "Execution & runtime"),
    ("inference-and-providers", "Inference & providers"),
    ("platform-and-tooling", "Platform & tooling"),
)

# The macro that adopts any subsystem not explicitly assigned in
# :data:`_SUBSYSTEM_SECTIONS` — keeps a newly-added ``pipelex.<area>`` reachable
# in the nav (under a humanized heading) without a manifest edit. Must be one of
# the :data:`_MACRO_SECTIONS` slugs.
_FALLBACK_MACRO_SLUG = "platform-and-tooling"

# Curated subsystem sections, in display order *within* their macro. Each entry
# is ``(subsystem_key, macro_slug, heading)``. ``subsystem_key`` is the second
# segment of a class's defining module (``pipelex.<subsystem>.…``) — the layer
# that groups errors by the area of the codebase they originate from. A subsystem
# missing from this tuple still renders: it lands in the fallback macro under a
# humanized heading (see :func:`_subsystems_for_macro`), so adding a new
# ``pipelex/<area>/…_exceptions.py`` needs no edit here — the curation only pins
# label wording, macro placement, and ordering, never completeness.
_SUBSYSTEM_SECTIONS: tuple[tuple[str, str, str], ...] = (
    # Authoring & language
    ("mthds_parsing", "authoring-and-language", "MTHDS parsing"),
    ("core", "authoring-and-language", "Core language"),
    ("pipe_operators", "authoring-and-language", "Pipe operators"),
    ("pipe_controllers", "authoring-and-language", "Pipe controllers"),
    ("pipe_signature", "authoring-and-language", "Pipe signatures"),
    ("builder", "authoring-and-language", "Builder"),
    ("libraries", "authoring-and-language", "Libraries"),
    # Execution & runtime
    ("pipe_run", "execution-and-runtime", "Pipe execution"),
    ("pipeline", "execution-and-runtime", "Pipeline execution"),
    ("runtime_bridge", "execution-and-runtime", "Runtime bridge"),
    ("graph", "execution-and-runtime", "Graph"),
    ("tracing", "execution-and-runtime", "Tracing"),
    # Inference & providers
    ("cogt", "inference-and-providers", "Inference (Cogt)"),
    ("plugins", "inference-and-providers", "Provider plugins"),
    # Platform & tooling
    ("base_exceptions", "platform-and-tooling", "Base & root errors"),
    ("tools", "platform-and-tooling", "Tools"),
    ("kit", "platform-and-tooling", "Kit"),
    ("system", "platform-and-tooling", "System & configuration"),
    ("cli", "platform-and-tooling", "CLI"),
)


def _subsystem_key(cls: type[PipelexError]) -> str:
    """Return the subsystem grouping key for ``cls`` — the second segment of its module path.

    Every ``PipelexError`` subclass lives at ``pipelex.<subsystem>.…exceptions``
    (root errors live directly in ``pipelex.base_exceptions``), so the second
    dotted segment names the area of the codebase the error belongs to. That is
    the axis the listing pages group on.
    """
    parts = cls.__module__.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def _humanize_subsystem(key: str) -> str:
    """Fallback heading for an uncurated subsystem ``key`` (snake_case → Sentence case)."""
    return key.replace("_", " ").capitalize()


def _group_by_subsystem(classes: Iterable[type[PipelexError]]) -> dict[str, list[type[PipelexError]]]:
    """Bucket ``classes`` by :func:`_subsystem_key`, each bucket alphabetized by class name."""
    by_subsystem: dict[str, list[type[PipelexError]]] = {}
    for cls in sorted(classes, key=lambda c: c.__name__):
        by_subsystem.setdefault(_subsystem_key(cls), []).append(cls)
    return by_subsystem


def _subsystems_for_macro(
    *,
    macro_slug: str,
    by_subsystem: dict[str, list[type[PipelexError]]],
) -> list[tuple[str, list[type[PipelexError]]]]:
    """Return the ``(heading, classes)`` subsystem sections that belong on a macro page.

    Curated subsystems assigned to ``macro_slug`` come first, in
    :data:`_SUBSYSTEM_SECTIONS` order. The fallback macro additionally adopts any
    uncurated subsystem present, appended alphabetically under a humanized
    heading. Subsystems with no loaded classes are skipped, so a macro with
    nothing to show yields an empty list and no page is written.
    """
    sections: list[tuple[str, list[type[PipelexError]]]] = []
    for key, assigned_macro, heading in _SUBSYSTEM_SECTIONS:
        if assigned_macro == macro_slug and key in by_subsystem:
            sections.append((heading, by_subsystem[key]))
    if macro_slug == _FALLBACK_MACRO_SLUG:
        curated = {key for key, _, _ in _SUBSYSTEM_SECTIONS}
        for key in sorted(by_subsystem):
            if key not in curated:
                sections.append((_humanize_subsystem(key), by_subsystem[key]))
    return sections


def render_macro_page(*, macro_heading: str, sections: list[tuple[str, list[type[PipelexError]]]]) -> str:
    """Render one macro listing page: a ``## subsystem`` block per section, class links beneath.

    ``sections`` is the output of :func:`_subsystems_for_macro` — already ordered
    and non-empty.
    """
    description = f"Pipelex error classes in the {macro_heading} area, grouped by subsystem."
    lines: list[str] = [
        "---",
        f'title: "{macro_heading}"',
        f'description: "{description}"',
        "---",
        "",
        f"{GENERATED_MARKER}",
        "",
        f"# {macro_heading}",
        "",
        "Each error class below has a stable RFC 7807 `type` URI that dereferences to its",
        "own page. Classes are grouped by subsystem.",
        "",
    ]
    for heading, classes in sections:
        lines.append(f"## {heading}")
        lines.append("")
        for cls in classes:
            lines.append(f"- [`{cls.__name__}`]({page_slug(cls)}.md) — {cls.title()}")
        lines.append("")
    lines.append("[Back to Error Reference](index.md)")
    lines.append("")
    return "\n".join(lines)


def render_index_page(by_subsystem: dict[str, list[type[PipelexError]]]) -> str:
    """Render the Error Reference overview that links to each macro listing page.

    The overview stays light: it explains the ``type`` URI contract and lists the
    macro sections (in :data:`_MACRO_SECTIONS` order), each annotated with the
    subsystems it covers — derived live from ``by_subsystem`` so the annotation
    never drifts from what the macro pages actually contain. A macro with no
    loaded classes is omitted.
    """
    lines: list[str] = [
        "---",
        'title: "Error Reference"',
        'description: "Auto-generated overview of the Pipelex error reference, grouped into macro areas of error classes."',
        "---",
        "",
        f"{GENERATED_MARKER}",
        "<!-- This index is generated by `pipelex-dev generate-error-pages`. To claim this",
        "     page for hand-editing, add a standalone `pipelex:authored` HTML comment line;",
        "     the generator will then preserve it on every run. -->",
        "",
        "# Error Reference",
        "",
        "Every Pipelex error class has a stable RFC 7807 `type` URI on the form",
        "`<base_uri>/<kebab-class-name>/`, and that URI dereferences to a per-class page.",
        "The classes are grouped into a few macro areas — pick the one that matches where",
        "the error came from:",
        "",
    ]
    for macro_slug, macro_heading in _MACRO_SECTIONS:
        sections = _subsystems_for_macro(macro_slug=macro_slug, by_subsystem=by_subsystem)
        if not sections:
            continue
        covered = ", ".join(heading for heading, _ in sections)
        lines.append(f"- [{macro_heading}]({macro_slug}.md) — {covered}.")
    lines.extend(
        [
            "",
            "See [Error Model](../under-the-hood/error-model.md) for the underlying contract",
            "and classification rules.",
            "",
        ]
    )
    return "\n".join(lines)


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
