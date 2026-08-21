class DoclingSdk:
    def __init__(self):
        # Deferred import: avoid pulling heavy SDK at module-load time
        from docling.document_converter import DocumentConverter  # ruff: ignore[import-outside-top-level]

        self.document_converter: DocumentConverter = DocumentConverter()
