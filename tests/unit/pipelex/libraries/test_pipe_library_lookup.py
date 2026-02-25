from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.libraries.pipe.pipe_library import PipeLibrary


def _make_stub_pipe(mocker: MockerFixture, code: str, domain_code: str) -> Any:
    """Create a minimal mock pipe with code and domain_code."""
    mock_pipe = mocker.MagicMock()
    mock_pipe.code = code
    mock_pipe.domain_code = domain_code
    return mock_pipe


class TestPipeLibraryLookup:
    """Tests for PipeLibrary.get_optional_pipe domain enforcement and malformed-ref safety."""

    def test_bare_code_lookup(self, mocker: MockerFixture):
        """Bare code lookup still works."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["compute_score"] = mock_pipe
        result = library.get_optional_pipe("compute_score")
        assert result is mock_pipe

    def test_domain_qualified_ref_correct_domain(self, mocker: MockerFixture):
        """Domain-qualified ref resolves when pipe domain matches."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["compute_score"] = mock_pipe
        result = library.get_optional_pipe("scoring.compute_score")
        assert result is mock_pipe

    def test_domain_qualified_ref_wrong_domain(self, mocker: MockerFixture):
        """Domain-qualified ref returns None when pipe domain does not match."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["compute_score"] = mock_pipe
        result = library.get_optional_pipe("wrong_domain.compute_score")
        assert result is None

    def test_cross_package_ref_correct_domain(self, mocker: MockerFixture):
        """Cross-package ref resolves when pipe domain matches."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.add_dependency_pipe(alias="lib", pipe=mock_pipe)
        result = library.get_optional_pipe("lib->scoring.compute_score")
        assert result is mock_pipe

    def test_cross_package_ref_wrong_domain(self, mocker: MockerFixture):
        """Cross-package ref returns None when pipe domain does not match."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.add_dependency_pipe(alias="lib", pipe=mock_pipe)
        result = library.get_optional_pipe("lib->wrong_domain.compute_score")
        assert result is None

    @pytest.mark.parametrize(
        "malformed_ref",
        [
            "foo..bar",
            ".foo",
            "foo.",
        ],
    )
    def test_malformed_dotted_ref_returns_none(self, malformed_ref: str):
        """Malformed dotted refs return None instead of raising."""
        library = PipeLibrary.make_empty()
        result = library.get_optional_pipe(malformed_ref)
        assert result is None

    @pytest.mark.parametrize(
        "malformed_ref",
        [
            "lib->foo..bar",
            "lib->.foo",
            "lib->foo.",
        ],
    )
    def test_malformed_cross_package_ref_returns_none(self, malformed_ref: str):
        """Malformed cross-package refs return None instead of raising."""
        library = PipeLibrary.make_empty()
        result = library.get_optional_pipe(malformed_ref)
        assert result is None

    def test_get_required_pipe_malformed_raises_not_found(self):
        """Malformed ref through get_required_pipe raises PipeNotFoundError, not QualifiedRefError."""
        library = PipeLibrary.make_empty()
        with pytest.raises(PipeNotFoundError):
            library.get_required_pipe("foo..bar")

    def test_get_required_pipe_domain_mismatch_raises_not_found(self, mocker: MockerFixture):
        """Domain mismatch through get_required_pipe raises PipeNotFoundError."""
        library = PipeLibrary.make_empty()
        mock_pipe = _make_stub_pipe(mocker, code="compute_score", domain_code="scoring")
        library.root["compute_score"] = mock_pipe
        with pytest.raises(PipeNotFoundError):
            library.get_required_pipe("wrong_domain.compute_score")
