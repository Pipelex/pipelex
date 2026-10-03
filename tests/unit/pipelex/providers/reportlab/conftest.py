import pytest

from pipelex.providers.reportlab.pdf_elements import register_bundled_fonts


@pytest.fixture(autouse=True, scope="session")
def bundled_fonts_registered() -> None:
    """Paragraphs and text measures need the bundled fonts registered, which the engine does only when it is built."""
    register_bundled_fonts()
