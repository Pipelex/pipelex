"""Unit tests for ``PipelexError.title()`` / ``type_uri()`` and end-to-end
``to_error_report()`` population. These need the Pipelex config loaded
(the standard pytest fixture chain handles bootstrapping).
"""

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexConfigError, PipelexError, SecurityError
from pipelex.mthds_parsing.exceptions import BundleElaboratorError, MthdsParserError


class TestPipelexErrorTitleAndTypeUri:
    def test_to_error_report_populates_title_and_type_uri(self) -> None:
        """``to_error_report()`` populates ``title`` / ``type_uri`` from the class methods."""
        report = PipelexConfigError("bad config").to_error_report()
        assert report.title == "Pipelex config"
        assert report.type_uri == "https://docs.pipelex.com/latest/errors/pipelex-config-error/"
        assert report.error_domain == ErrorDomain.CONFIG

    def test_auto_derive_title(self) -> None:
        """A subclass with no ``_declared_title`` auto-derives from the class name."""

        class FooBarError(PipelexError):
            pass

        assert FooBarError.title() == "Foo bar"
        assert FooBarError.type_uri() == "https://docs.pipelex.com/latest/errors/foo-bar-error/"

    def test_declared_title_wins_over_auto_derive(self) -> None:
        """``_declared_title`` set on a subclass overrides the auto-derived title."""

        class HasCuratedTitleError(PipelexError):
            _declared_title = "Curated title"

        assert HasCuratedTitleError.title() == "Curated title"
        # type_uri still auto-derives unless _declared_type_uri is also set.
        assert HasCuratedTitleError.type_uri() == "https://docs.pipelex.com/latest/errors/has-curated-title-error/"

    def test_declared_type_uri_wins_over_auto_derive(self) -> None:
        """``_declared_type_uri`` set on a subclass overrides the auto-derived URI."""

        class CustomUriError(PipelexError):
            _declared_type_uri = "https://example.com/custom-error"

        assert CustomUriError.type_uri() == "https://example.com/custom-error"

    def test_declared_title_does_not_leak_through_inheritance(self) -> None:
        """A parent's ``_declared_title`` is not silently inherited — each class
        either declares its own title or auto-derives from its own name.

        ``SecurityError`` curates ``"Security policy violation"``. A bare
        subclass should NOT inherit that — it should auto-derive from its own
        class name.
        """

        class CustomSecurityError(SecurityError):
            pass

        assert CustomSecurityError.title() == "Custom security"

    def test_curated_titles_for_high_traffic_classes(self) -> None:
        """The curated ``_declared_title`` overrides shipped with Item A."""
        assert PipelexError.title() == "Pipelex error"
        assert SecurityError.title() == "Security policy violation"

    def test_mthds_parser_error_identity_is_pinned(self) -> None:
        """The parser error's wire-visible identity triple, pinned against silent drift.

        ``error_type`` (the class name), ``title`` and ``type_uri`` all travel on every
        ``ErrorReport``, and clients branch on them. Nothing asserted the trio before, which is
        how a rename left the repo's own fixtures carrying a shape the class cannot produce.
        The title is *declared* rather than auto-derived because ``_humanize_class_name`` would
        render the standard's name as "Mthds parser" — see ``mthds_parsing/exceptions.py``.
        """
        report = MthdsParserError("bad .mthds").to_error_report()
        assert report.error_type == "MthdsParserError"
        assert report.title == "MTHDS parser"
        assert report.type_uri == "https://docs.pipelex.com/latest/errors/mthds-parser-error/"

        # The declared title must not capture the subclass — it derives from its own name.
        assert BundleElaboratorError.title() == "Bundle elaborator"
        assert BundleElaboratorError.type_uri() == "https://docs.pipelex.com/latest/errors/bundle-elaborator-error/"

    def test_round_trip_preserves_title_and_type_uri(self) -> None:
        """``ErrorReport.from_dict(report.to_dict())`` preserves the new fields."""
        report = PipelexConfigError("config gone").to_error_report()
        recovered = ErrorReport.from_dict(report.to_dict())
        assert recovered.title == report.title
        assert recovered.type_uri == report.type_uri
        assert recovered == report
