from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.error_registry.exceptions import ErrorRegistryError
from pipelex.cli.dev_cli.commands.error_registry.type_redirects import STUB_MARKER, write_type_redirects

if TYPE_CHECKING:
    from pathlib import Path

BASE_URL = "https://docs.pipelex.com/errors"


def _publish_page(site_root: Path, *, version: str, page_dir: str) -> None:
    page_path = site_root / version / "errors" / page_dir / "index.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("<html>page</html>", encoding="utf-8")


class TestTypeRedirects:
    def test_a_stub_per_documented_code_redirects_its_type_uri_to_the_latest_page(self, tmp_path: Path) -> None:
        """The type URI's directory, named after the whole code, redirects to the code's page under /latest/."""
        _publish_page(tmp_path, version="latest", page_dir="pipelex/billing/credit_exhausted")
        _publish_page(tmp_path, version="latest", page_dir="pipelex/config/syntax")
        _publish_page(tmp_path, version="0.86.0", page_dir="pipelex/old/code")

        report = write_type_redirects(site_root=tmp_path, base_url=BASE_URL)

        assert report.written == ["pipelex.billing.credit_exhausted", "pipelex.config.syntax", "(index)"]
        stub = (tmp_path / "errors" / "pipelex.billing.credit_exhausted" / "index.html").read_text(encoding="utf-8")
        assert STUB_MARKER in stub
        assert '<meta http-equiv="refresh" content="0; url=/latest/errors/pipelex/billing/credit_exhausted/">' in stub
        assert '<link rel="canonical" href="https://docs.pipelex.com/latest/errors/pipelex/billing/credit_exhausted/">' in stub
        index_stub = (tmp_path / "errors" / "index.html").read_text(encoding="utf-8")
        assert "url=/latest/errors/" in index_stub
        assert not (tmp_path / "errors" / "pipelex.old.code").exists()

    def test_a_second_run_changes_nothing_and_a_stale_stub_is_removed(self, tmp_path: Path) -> None:
        """Rerunning is idempotent; a stub whose code latest no longer documents goes, a directory the tool did not write stays."""
        _publish_page(tmp_path, version="latest", page_dir="pipelex/billing/credit_exhausted")
        _publish_page(tmp_path, version="latest", page_dir="pipelex/billing/plan_limit")
        write_type_redirects(site_root=tmp_path, base_url=BASE_URL)
        foreign_dir = tmp_path / "errors" / "pipelex.hand.written"
        foreign_dir.mkdir()
        (foreign_dir / "index.html").write_text("<html>mine</html>", encoding="utf-8")

        report = write_type_redirects(site_root=tmp_path, base_url=BASE_URL)
        assert report.written == []
        assert report.removed == []
        assert sorted(report.unchanged) == ["(index)", "pipelex.billing.credit_exhausted", "pipelex.billing.plan_limit"]

        (tmp_path / "latest" / "errors" / "pipelex" / "billing" / "plan_limit" / "index.html").unlink()
        report = write_type_redirects(site_root=tmp_path, base_url=BASE_URL)
        assert report.removed == ["pipelex.billing.plan_limit"]
        assert not (tmp_path / "errors" / "pipelex.billing.plan_limit").exists()
        assert (foreign_dir / "index.html").is_file()

    def test_a_site_without_a_latest_version_is_refused(self, tmp_path: Path) -> None:
        """With no released version there is no page for a type URI to reach."""
        with pytest.raises(ErrorRegistryError, match="holds no 'latest' version"):
            write_type_redirects(site_root=tmp_path, base_url=BASE_URL)

    def test_a_base_url_without_a_path_is_refused(self, tmp_path: Path) -> None:
        """Stubs written at the site's very root would overwrite its own pages."""
        (tmp_path / "latest").mkdir()
        with pytest.raises(ErrorRegistryError, match="has no path"):
            write_type_redirects(site_root=tmp_path, base_url="https://docs.pipelex.com")
