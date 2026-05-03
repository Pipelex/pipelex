class DoclingSdk:
    def __init__(self):
        # Deferred import: avoid pulling heavy SDK at module-load time
        from docling.document_converter import DocumentConverter  # noqa: PLC0415

        self.document_converter: DocumentConverter = DocumentConverter()
