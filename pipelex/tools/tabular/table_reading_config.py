from typing import Annotated

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class TableReadingConfig(ConfigModel):
    """`[runtime.table_reading]`: how large a spreadsheet the runtime reads into records.

    Whoever supplies the file chooses its size, and an Excel workbook is a ZIP archive whose few compressed kilobytes can
    declare millions of cells, so both bounds are checked before the cells are read, and a file past either is refused as
    ``input.too_large``:

    - ``max_workbook_uncompressed_bytes`` is the most bytes the parts of an Excel workbook (`.xlsx`) may hold once
      decompressed, summed from the sizes its archive declares before anything is decompressed. The workbook is loaded
      whole into memory, so this bounds the memory a load takes.
    - ``max_table_cells`` is the most cells, rows times columns, the Table read may span, counted over the part of the
      Table's declared range that the sheet actually fills, so a Table declaring a range far larger than its sheet costs
      only what the sheet holds.
    """

    max_workbook_uncompressed_bytes: Annotated[int, Field(ge=1)]
    max_table_cells: Annotated[int, Field(ge=1)]
