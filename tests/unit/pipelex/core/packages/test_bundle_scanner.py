from pathlib import Path

import pytest

from pipelex.core.packages.bundle_scanner import build_domain_exports_from_scan, scan_bundles_for_domain_info

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


class TestBundleScanner:
    """Tests for the shared bundle scanning and domain-exports-building functions."""

    def test_scan_bundles_extracts_domains_and_pipes(self):
        """Scanning multi-domain .mthds files returns correct domain/pipe mappings."""
        mthds_files = sorted(PACKAGES_DATA_DIR.joinpath("legal_tools").rglob("*.mthds"))
        assert len(mthds_files) >= 2, "Expected at least two .mthds fixtures"

        domain_pipes, domain_main_pipes, errors = scan_bundles_for_domain_info(mthds_files)

        assert not errors
        assert "pkg_test_legal.contracts" in domain_pipes
        assert "pkg_test_scoring" in domain_pipes
        assert "pkg_test_extract_clause" in domain_pipes["pkg_test_legal.contracts"]
        assert "pkg_test_analyze_contract" in domain_pipes["pkg_test_legal.contracts"]
        assert "pkg_test_compute_weighted_score" in domain_pipes["pkg_test_scoring"]
        assert domain_main_pipes["pkg_test_legal.contracts"] == "pkg_test_extract_clause"
        assert domain_main_pipes["pkg_test_scoring"] == "pkg_test_compute_weighted_score"

    def test_scan_bundles_collects_parse_errors(self, tmp_path: Path):
        """Files that cannot be parsed are collected as error strings."""
        bad_file = tmp_path / "broken.mthds"
        bad_file.write_text("[broken\n", encoding="utf-8")

        _domain_pipes, _domain_main_pipes, errors = scan_bundles_for_domain_info([bad_file])

        assert len(errors) == 1
        assert str(bad_file) in errors[0]

    def test_scan_bundles_handles_empty_input(self):
        """Passing no files returns empty results."""
        domain_pipes, domain_main_pipes, errors = scan_bundles_for_domain_info([])

        assert domain_pipes == {}
        assert domain_main_pipes == {}
        assert errors == []

    def test_build_exports_main_pipe_first(self):
        """Main pipe appears first in the exports pipe list, remaining sorted."""
        domain_pipes = {
            "alpha": ["zebra_pipe", "alpha_pipe", "main_alpha"],
        }
        domain_main_pipes = {
            "alpha": "main_alpha",
        }

        exports = build_domain_exports_from_scan(domain_pipes, domain_main_pipes)

        assert len(exports) == 1
        assert exports[0].domain_path == "alpha"
        assert exports[0].pipes[0] == "main_alpha"
        assert exports[0].pipes == ["main_alpha", "alpha_pipe", "zebra_pipe"]

    def test_build_exports_skips_empty_domains(self):
        """Domains with no pipes produce no exports entry."""
        domain_pipes = {
            "has_pipes": ["some_pipe"],
            "empty_domain": [],
        }
        domain_main_pipes: dict[str, str] = {}

        exports = build_domain_exports_from_scan(domain_pipes, domain_main_pipes)

        assert len(exports) == 1
        assert exports[0].domain_path == "has_pipes"

    def test_build_exports_sorts_domains(self):
        """Domains appear in sorted order in the exports list."""
        domain_pipes = {
            "zebra_domain": ["pipe_z"],
            "alpha_domain": ["pipe_a"],
        }
        domain_main_pipes: dict[str, str] = {}

        exports = build_domain_exports_from_scan(domain_pipes, domain_main_pipes)

        assert len(exports) == 2
        assert exports[0].domain_path == "alpha_domain"
        assert exports[1].domain_path == "zebra_domain"

    def test_scan_bundles_detects_main_pipe_conflict(self, tmp_path: Path):
        """Two bundles sharing a domain but declaring different main_pipe produce an error."""
        bundle_a = tmp_path / "bundle_a.mthds"
        bundle_a.write_text(
            'domain = "shared_domain"\n'
            'main_pipe = "pipe_alpha"\n'
            "\n"
            "[pipe.pipe_alpha]\n"
            'type = "PipeLLM"\n'
            'description = "Alpha"\n'
            'output = "Text"\n'
            'prompt = "alpha"\n',
            encoding="utf-8",
        )
        bundle_b = tmp_path / "bundle_b.mthds"
        bundle_b.write_text(
            'domain = "shared_domain"\n'
            'main_pipe = "pipe_beta"\n'
            "\n"
            "[pipe.pipe_beta]\n"
            'type = "PipeLLM"\n'
            'description = "Beta"\n'
            'output = "Text"\n'
            'prompt = "beta"\n',
            encoding="utf-8",
        )

        _domain_pipes, domain_main_pipes, errors = scan_bundles_for_domain_info(
            sorted([bundle_a, bundle_b]),
        )

        assert len(errors) == 1
        assert "shared_domain" in errors[0]
        assert "pipe_alpha" in errors[0]
        assert "pipe_beta" in errors[0]
        assert str(bundle_b) in errors[0]
        # First value kept, conflict reported but not overwritten
        assert domain_main_pipes["shared_domain"] == "pipe_alpha"

    def test_scan_bundles_allows_identical_main_pipe(self, tmp_path: Path):
        """Two bundles declaring the same main_pipe for a domain is not an error."""
        bundle_a = tmp_path / "bundle_a.mthds"
        bundle_a.write_text(
            'domain = "shared_domain"\n'
            'main_pipe = "same_pipe"\n'
            "\n"
            "[pipe.same_pipe]\n"
            'type = "PipeLLM"\n'
            'description = "A"\n'
            'output = "Text"\n'
            'prompt = "a"\n',
            encoding="utf-8",
        )
        bundle_b = tmp_path / "bundle_b.mthds"
        bundle_b.write_text(
            'domain = "shared_domain"\n'
            'main_pipe = "same_pipe"\n'
            "\n"
            "[pipe.same_pipe]\n"
            'type = "PipeLLM"\n'
            'description = "B copy"\n'
            'output = "Text"\n'
            'prompt = "b"\n',
            encoding="utf-8",
        )

        _domain_pipes, domain_main_pipes, errors = scan_bundles_for_domain_info(
            sorted([bundle_a, bundle_b]),
        )

        assert not errors
        assert domain_main_pipes["shared_domain"] == "same_pipe"

    @pytest.mark.parametrize(
        ("topic", "domain_pipes", "domain_main_pipes", "expected_first_pipe"),
        [
            (
                "main_pipe present and also in pipe list",
                {"dom": ["other", "main_p"]},
                {"dom": "main_p"},
                "main_p",
            ),
            (
                "main_pipe not in pipe list",
                {"dom": ["other"]},
                {"dom": "main_p"},
                "main_p",
            ),
            (
                "no main_pipe",
                {"dom": ["beta", "alpha"]},
                {},
                "alpha",
            ),
        ],
    )
    def test_build_exports_main_pipe_ordering(
        self,
        topic: str,
        domain_pipes: dict[str, list[str]],
        domain_main_pipes: dict[str, str],
        expected_first_pipe: str,
    ):
        """Main pipe ordering scenarios."""
        _ = topic  # Used for test identification
        exports = build_domain_exports_from_scan(domain_pipes, domain_main_pipes)
        assert exports[0].pipes[0] == expected_first_pipe
