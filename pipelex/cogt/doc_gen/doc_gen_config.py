from pipelex.system.configuration.config_model import ConfigModel


class DocGenConfig(ConfigModel):
    """How the runtime prints the documents `PipeDocGen` steps ask for.

    ``engines`` chooses the document engine that prints a format from a source when more than one installed
    engine does, keyed ``"<format>.<source>"`` (``"pdf.layout"``). A format and source that one installed
    engine alone prints need no entry, and one that no installed engine prints is refused when the method
    loads, whatever this says.
    """

    engines: dict[str, str]
