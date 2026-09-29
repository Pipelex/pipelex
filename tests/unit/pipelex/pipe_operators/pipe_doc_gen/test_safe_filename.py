import pytest

from pipelex.pipe_operators.doc_gen.pipe_doc_gen import safe_filename


class TestSafeFilename:
    @pytest.mark.parametrize(
        ("rendered", "expected"),
        [
            ("invoice-INV-2026-0142", "invoice-INV-2026-0142.pdf"),
            ("invoice INV/2026:0142", "invoice-INV-2026-0142.pdf"),
            ("report.pdf", "report.pdf"),
            ("  ../../etc/passwd  ", "etc-passwd.pdf"),
            ("", "render_invoice.pdf"),
            ("...", "render_invoice.pdf"),
        ],
    )
    def test_the_rendered_name_becomes_one_safe_segment(self, rendered: str, expected: str) -> None:
        assert safe_filename(rendered=rendered, fallback="render_invoice", suffix="pdf") == expected
