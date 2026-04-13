class DoclingSdk:
    def __init__(self):
        from docling.document_converter import DocumentConverter  # noqa: PLC0415

        self.document_converter: DocumentConverter = DocumentConverter()
